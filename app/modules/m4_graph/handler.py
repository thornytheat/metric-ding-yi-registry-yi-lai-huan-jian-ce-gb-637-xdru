"""M4 入口：依赖图、环分量、同名冲突、图页面。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ... import errors
from ...web import Ctx, get_ctx, render
from . import service

router = APIRouter(tags=["M4 依赖图与环"])


def _batch(ctx: Ctx, batch_id: str | None) -> dict:
    batch = ctx.current_batch(batch_id)
    if batch is None:
        raise errors.NotFound("还没有批次，先解析一次", code="E_EMPTY_INPUT")
    return batch


@router.get("/api/graph")
def api_graph(batch_id: str | None = None, ctx: Ctx = Depends(get_ctx)) -> dict:
    batch = _batch(ctx, batch_id)
    payload = service.graph_view(ctx.store, batch["batch_id"])
    payload["batch_id"] = batch["batch_id"]
    return payload


@router.get("/graph")
def page_graph(request: Request, batch_id: str | None = None,
               ctx: Ctx = Depends(get_ctx)):
    batch = ctx.current_batch(batch_id)
    payload = {"nodes": [], "edges": [], "components": [], "cycles": [],
               "conflicts": [], "counts": {"nodes": 0, "edges": 0, "components": 0,
                                           "cycles": 0, "cycle_metrics": 0},
               "by_kind": {}, "by_edge": {}, "edge_labels": {}}
    if batch is not None:
        payload = service.graph_view(ctx.store, batch["batch_id"])
    return render(request, "graph.html", batch=batch, page="graph",
                  payload=payload, page_title="依赖图与环")
