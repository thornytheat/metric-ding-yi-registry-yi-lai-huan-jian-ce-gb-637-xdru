"""M2 入口：契约查询、原因码目录、单行试解析、文法页。"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request

from ... import reasons
from ...web import Ctx, get_ctx, render
from . import service

router = APIRouter(tags=["M2 语法规则"])



@router.get("/api/contract")
def api_contract(ctx: Ctx = Depends(get_ctx)) -> dict:
    payload = service.contract_view(ctx.settings)
    payload["reasons"] = reasons.catalog()
    return payload


@router.post("/api/syntax/preview")
def api_preview(payload: dict | None = Body(default=None)) -> dict:
    text = payload.get("text") if isinstance(payload, dict) else ""
    return service.preview(text if isinstance(text, str) else "")


@router.get("/contract")
def page_contract(request: Request, ctx: Ctx = Depends(get_ctx)):
    payload = service.contract_view(ctx.settings)
    return render(request, "contract.html", batch=ctx.current_batch(),
                  page="contract", payload=payload,
                  reason_rows=reasons.catalog(), page_title="语法与字段登记")
