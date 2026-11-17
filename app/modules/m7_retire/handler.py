"""M7 入口：下线影响、迁移次序、阻断项、清单导出、下线页。"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request, Response

from ... import errors, reasons
from ...web import Ctx, get_ctx, render
from . import service

router = APIRouter(tags=["M7 下线影响与迁移顺序"])


def _batch(ctx: Ctx, batch_id: str | None) -> dict:
    batch = ctx.current_batch(batch_id)
    if batch is None:
        raise errors.NotFound("还没有批次，先解析一次", code="E_EMPTY_INPUT")
    return batch


def _targets(payload) -> list[str] | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("targets")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]
    return None


@router.get("/api/retire")
def api_retire(targets: str | None = None, batch_id: str | None = None,
               ctx: Ctx = Depends(get_ctx)) -> dict:
    batch = _batch(ctx, batch_id)
    return service.plan_for(ctx.store, ctx.settings, batch["batch_id"],
                            targets=targets, strict=True)


@router.post("/api/retire")
def api_retire_post(payload: dict | None = Body(default=None),
                    batch_id: str | None = None,
                    ctx: Ctx = Depends(get_ctx)) -> dict:
    batch = _batch(ctx, batch_id)
    targets = _targets(payload)
    if targets is None:
        raise errors.BadRequest("请求体缺少 targets", code="R_NO_TARGETS",
                                detail={"hint": "targets 用逗号分隔指标名"})
    return service.plan_for(ctx.store, ctx.settings, batch["batch_id"],
                            targets=targets, strict=True)


@router.get("/api/retire/order.csv")
def api_retire_order(targets: str | None = None, batch_id: str | None = None,
                     ctx: Ctx = Depends(get_ctx)) -> Response:
    batch = _batch(ctx, batch_id)
    payload = service.plan_for(ctx.store, ctx.settings, batch["batch_id"],
                               targets=targets, strict=True)
    return Response(
        content=service.order_csv(payload).encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="metricreg-retire-{batch["batch_id"]}.csv"'})


@router.get("/retire")
def page_retire(request: Request, batch_id: str | None = None,
                targets: str | None = None, ctx: Ctx = Depends(get_ctx)):
    batch = ctx.current_batch(batch_id)
    payload = service.empty_payload()
    if batch is not None:
        try:
            payload = service.page_payload(ctx.store, ctx.settings,
                                           batch["batch_id"], targets=targets)
        except errors.MetricregError as exc:
            payload["notice"] = f"{exc.code} {exc.message}"
    return render(request, "retire.html", batch=batch, page="retire",
                  payload=payload, reasons=reasons,
                  level_labels={"error": "阻断", "warn": "提示", "info": "记录"},
                  page_title="下线与迁移顺序")
