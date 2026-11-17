"""M6 入口：影响面、四账、导出（CSV/JSON）、影响面页。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from ... import errors
from ...web import Ctx, get_ctx, render
from . import service

router = APIRouter(tags=["M6 影响面与导出"])


def _batch(ctx: Ctx, batch_id: str | None) -> dict:
    batch = ctx.current_batch(batch_id)
    if batch is None:
        raise errors.NotFound("还没有批次，先解析一次", code="E_EMPTY_INPUT")
    return batch


@router.get("/api/impact")
def api_impact(metric: str | None = None, batch_id: str | None = None,
               ctx: Ctx = Depends(get_ctx)) -> dict:
    batch = _batch(ctx, batch_id)
    payload = service.impact_view(ctx.store, batch["batch_id"], metric)
    payload["batch_id"] = batch["batch_id"]
    return payload


@router.get("/api/reconcile")
def api_reconcile(batch_id: str | None = None, ctx: Ctx = Depends(get_ctx)) -> dict:
    batch = _batch(ctx, batch_id)
    payload = service.reconcile_view(ctx.store, batch["batch_id"])
    payload["batch_id"] = batch["batch_id"]
    return payload


@router.get("/api/export/metrics.csv")
def api_export_metrics(batch_id: str | None = None,
                       ctx: Ctx = Depends(get_ctx)) -> Response:
    batch = _batch(ctx, batch_id)
    bundle = service.export_bundle(ctx.store, batch["batch_id"])
    return _csv(bundle["metrics_csv"], f"metricreg-metrics-{batch['batch_id']}.csv")


@router.get("/api/export/edges.csv")
def api_export_edges(batch_id: str | None = None,
                     ctx: Ctx = Depends(get_ctx)) -> Response:
    batch = _batch(ctx, batch_id)
    bundle = service.export_bundle(ctx.store, batch["batch_id"])
    return _csv(bundle["edges_csv"], f"metricreg-edges-{batch['batch_id']}.csv")


@router.get("/api/export/conflicts.csv")
def api_export_conflicts(batch_id: str | None = None,
                         ctx: Ctx = Depends(get_ctx)) -> Response:
    batch = _batch(ctx, batch_id)
    bundle = service.export_bundle(ctx.store, batch["batch_id"])
    return _csv(bundle["conflicts_csv"], f"metricreg-conflicts-{batch['batch_id']}.csv")


@router.get("/api/export/manifest.json")
def api_export_manifest(batch_id: str | None = None,
                        ctx: Ctx = Depends(get_ctx)) -> Response:
    batch = _batch(ctx, batch_id)
    bundle = service.export_bundle(ctx.store, batch["batch_id"])
    return Response(content=bundle["manifest_json"].encode("utf-8"),
                    media_type="application/json; charset=utf-8",
                    headers={"Content-Disposition":
                             f'attachment; filename="metricreg-manifest-{batch["batch_id"]}.json"'})


def _csv(text: str, filename: str) -> Response:
    return Response(
        content=text.encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/impact")
def page_impact(request: Request, batch_id: str | None = None,
                metric: str | None = None, ctx: Ctx = Depends(get_ctx)):
    batch = ctx.current_batch(batch_id)
    payload = {"metric": "", "known": False, "downstream": [], "downstream_count": 0,
               "affected_reports": [], "weight_sum": "0.00", "score": "0.00",
               "report_count": 0, "ranking": [], "names": []}
    accounts_result = {"accounts": [], "all_balanced": True, "details": {}}
    if batch is not None:
        try:
            payload = service.impact_view(ctx.store, batch["batch_id"], metric)
        except errors.NotFound:
            payload["names"] = [m["name"] for m in
                                ctx.store.load_metrics(batch["batch_id"])]
        accounts_result = service.reconcile_view(ctx.store, batch["batch_id"])
    return render(request, "impact.html", batch=batch, page="impact",
                  payload=payload, accounts=accounts_result,
                  page_title="影响面与导出")
