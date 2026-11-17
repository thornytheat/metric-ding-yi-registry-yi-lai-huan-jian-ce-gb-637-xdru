"""M1 入口：触发一次解析、批次摘要、接入页。

请求体用普通 dict 接收（不依赖具体校验库版本），字段缺失按默认样例处理。
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request

from ... import errors
from ...web import Ctx, get_ctx, render
from . import service

router = APIRouter(tags=["M1 指标接入"])


def _field(payload, name: str, default=None):
    if isinstance(payload, dict):
        return payload.get(name, default)
    return default


@router.post("/api/import")
def api_import(payload: dict | None = Body(default=None),
               ctx: Ctx = Depends(get_ctx)) -> dict:
    text = _field(payload, "text")
    sample = _field(payload, "sample") or service.DEFAULT_SAMPLE
    if text is not None and not isinstance(text, str):
        raise errors.BadRequest("text 必须是字符串", code="E_EMPTY_INPUT")
    if text is None and sample not in (service.DEFAULT_SAMPLE, service.CLEAN_SAMPLE):
        raise errors.BadRequest("未知样例名", code="E_EMPTY_INPUT",
                                detail={"sample": sample})
    result = service.run(ctx.settings, ctx.store, text=text, sample=sample)
    batch = result["batch"]
    return {
        "status": "done",
        "reused": result["reused"],
        "note": result.get("note", ""),
        "batch_id": batch["batch_id"],
        "run_id": batch["run_id"],
        "batch_key": batch["batch_key"],
        "counters": result["counters"],
        "stages": result.get("stages", []),
    }


@router.get("/api/batch")
def api_batch(batch_id: str | None = None, ctx: Ctx = Depends(get_ctx)) -> dict:
    batch = ctx.current_batch(batch_id)
    if batch is None:
        raise errors.NotFound("还没有批次，先解析一次", code="E_EMPTY_INPUT")
    return {"batch": batch, "counters": ctx.store.load_totals(batch["batch_id"]),
            "manifest": ctx.store.load_manifest(batch["batch_id"])}


@router.get("/")
def page_index(request: Request, batch_id: str | None = None,
               ctx: Ctx = Depends(get_ctx)):
    batch = ctx.current_batch(batch_id)
    rows: list[dict] = []
    summary = {"total": 0, "blank": 0, "comment": 0, "definition": 0}
    totals: dict = {}
    stages: list[dict] = []
    if batch is not None:
        rows = ctx.store.load_lines(batch["batch_id"])
        summary = {
            "total": len(rows),
            "blank": sum(1 for r in rows if r["kind"] == "blank"),
            "comment": sum(1 for r in rows if r["kind"] == "comment"),
            "definition": sum(1 for r in rows if r["kind"] == "definition"),
        }
        totals = ctx.store.load_totals(batch["batch_id"])
        stages = (ctx.store.load_manifest(batch["batch_id"]) or {}).get("stages", [])
    return render(request, "index.html", batch=batch, page="index",
                  rows=rows, summary=summary, totals=totals, stages=stages,
                  page_title="指标接入与解析")
