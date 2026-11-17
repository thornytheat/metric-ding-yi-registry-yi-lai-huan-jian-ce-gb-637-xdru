"""M5 入口：版本台账、陈旧提交、批次历史、版本页。"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request

from ... import errors
from ...web import Ctx, get_ctx, render
from . import batches, service, stale

router = APIRouter(tags=["M5 版本区间与批次"])



def _batch(ctx: Ctx, batch_id: str | None) -> dict:
    batch = ctx.current_batch(batch_id)
    if batch is None:
        raise errors.NotFound("还没有批次，先解析一次", code="E_EMPTY_INPUT")
    return batch


@router.get("/api/versions")
def api_versions(batch_id: str | None = None, ctx: Ctx = Depends(get_ctx)) -> dict:
    batch = _batch(ctx, batch_id)
    payload = service.view(ctx.store.load_versions(batch["batch_id"]))
    payload["batch_id"] = batch["batch_id"]
    return payload


@router.post("/api/versions/submit")
def api_submit(payload: dict | None = Body(default=None), batch_id: str | None = None,
               ctx: Ctx = Depends(get_ctx)) -> dict:
    batch = _batch(ctx, batch_id)
    return stale.submit(ctx.store, batch, payload if isinstance(payload, dict) else {})


@router.get("/api/batches")
def api_batches(ctx: Ctx = Depends(get_ctx)) -> dict:
    rows = service.history(ctx.store)
    latest = ctx.store.latest_batch()
    return {"batches": rows, "latest": latest["batch_id"] if latest else None,
            "count": len(rows)}


@router.get("/versions")
def page_versions(request: Request, batch_id: str | None = None,
                  ctx: Ctx = Depends(get_ctx)):
    batch = ctx.current_batch(batch_id)
    payload = {"rows": [], "counts": {}, "total": 0, "metrics": [], "conflict_rows": []}
    if batch is not None:
        payload = service.view(ctx.store.load_versions(batch["batch_id"]))
    return render(request, "versions.html", batch=batch, page="versions",
                  payload=payload, history=batches.history(ctx.store),
                  page_title="版本区间与批次")
