"""M3 入口：诊断列表、隔离导出、诊断页。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from ... import errors
from ...web import Ctx, get_ctx, render
from . import service

router = APIRouter(tags=["M3 解析诊断"])


def _batch(ctx: Ctx, batch_id: str | None) -> dict:
    batch = ctx.current_batch(batch_id)
    if batch is None:
        raise errors.NotFound("还没有批次，先解析一次", code="E_EMPTY_INPUT")
    return batch


@router.get("/api/diagnostics")
def api_diagnostics(batch_id: str | None = None, code: str | None = None,
                    level: str | None = None, stage: str | None = None,
                    line_no: int | None = None, ctx: Ctx = Depends(get_ctx)) -> dict:
    batch = _batch(ctx, batch_id)
    payload = service.view(ctx.store.load_diagnostics(batch["batch_id"]),
                           code=code, level=level, stage=stage, line_no=line_no)
    payload["batch_id"] = batch["batch_id"]
    return payload


@router.get("/api/diagnostics/export.csv")
def api_diagnostics_csv(batch_id: str | None = None,
                        ctx: Ctx = Depends(get_ctx)) -> Response:
    batch = _batch(ctx, batch_id)
    body = service.export_csv(ctx.store.load_diagnostics(batch["batch_id"]))
    return Response(
        content=body.encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="metricreg-diagnostics-{batch["batch_id"]}.csv"'})


@router.get("/diagnostics")
def page_diagnostics(request: Request, batch_id: str | None = None,
                     code: str | None = None, level: str | None = None,
                     stage: str | None = None, ctx: Ctx = Depends(get_ctx)):
    batch = ctx.current_batch(batch_id)
    payload = {"rows": [], "total": 0, "filtered": 0, "distribution": [],
               "by_level": {"error": 0, "warn": 0, "info": 0},
               "filters": {"code": code or "", "level": level or "",
                           "stage": stage or ""}, "codes": []}
    if batch is not None:
        payload = service.view(ctx.store.load_diagnostics(batch["batch_id"]),
                               code=code, level=level, stage=stage)
    return render(request, "diagnostics.html", batch=batch, page="diagnostics",
                  payload=payload, page_title="诊断与隔离")
