"""模板渲染与共享视图上下文：过滤器、导航、当前批次。

页面只读 store，不做业务计算；数字格式化统一在这里，避免每页各写一套。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from . import config, reasons

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

NAV = (
    ("/", "接入", "index"),
    ("/contract", "语法", "contract"),
    ("/diagnostics", "诊断", "diagnostics"),
    ("/graph", "依赖", "graph"),
    ("/versions", "版本", "versions"),
    ("/impact", "影响", "impact"),
    ("/retire", "下线", "retire"),
)
STATUS_LABELS = {
    "done": "完成", "failed": "失败", "running": "运行中",
    "registered": "注册", "isolated": "隔离", "blank": "空行", "comment": "注释",
    "OK": "有效", "OVERLAP": "区间重叠", "INVERTED": "起止倒挂",
    "BAD_FROM": "起始无效", "UNKNOWN": "未注册",
    "BLOCK": "阻断", "REVIEW": "复核", "INFO": "记录",
}
KIND_LABELS = {"metric": "指标", "field": "字段", "dim": "维度", "report": "报表"}


@dataclass
class Ctx:
    settings: config.Settings
    store: object

    def current_batch(self, batch_id: str | None = None) -> dict | None:
        if batch_id:
            return self.store.get_batch(batch_id)
        return self.store.latest_batch()


def get_ctx(request: Request) -> Ctx:
    return request.app.state.ctx


def setup(app) -> None:
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    env = templates.env
    env.filters["status"] = lambda s: STATUS_LABELS.get(s, s or "—")
    env.filters["level"] = lambda s: reasons.LEVEL_LABELS.get(s, s)
    env.filters["mark"] = lambda s: reasons.LEVEL_MARKS.get(s, ".")
    env.filters["kind"] = lambda s: KIND_LABELS.get(s, s)
    env.filters["num"] = fmt_num
    env.filters["dec2"] = fmt_dec2
    env.filters["count"] = lambda v: f"{int(v):,}"
    env.filters["join"] = lambda v, sep=",": sep.join(str(x) for x in (v or []))
    env.filters["ts"] = lambda s: (s or "").replace("T", " ")[:19]
    env.filters["short"] = lambda s, n=12: (s or "")[:n]
    env.globals.update(
        nav=NAV,
        stage_flow=config.STAGE_FLOW,
        stage_labels=config.STAGE_LABELS,
        reason_catalog=reasons.catalog(),
        level_labels=reasons.LEVEL_LABELS,
        conflict_levels=config.CONFLICT_LEVELS,
        money=None,
        weight_unit="权重",
        timezone_label="Asia/Shanghai (+08:00)",
        generated_at=now_local().strftime("%Y-%m-%d %H:%M:%S"),
    )
    app.state.templates = templates


def render(request: Request, name: str, **context):
    ctx: Ctx = request.app.state.ctx
    batch = context.pop("batch", None)
    if batch is None:
        batch = ctx.current_batch(context.get("batch_id"))
    base = {
        "request": request,
        "ctx": ctx,
        "settings": ctx.settings,
        "batch": batch,
        "rule_version": ctx.settings.rule_version,
        "eval_date": ctx.settings.eval_date.isoformat(),
        "print_ts": now_local().strftime("%Y-%m-%d %H:%M"),
    }
    base.update(context)
    return request.app.state.templates.TemplateResponse(
        request=request, name=name, context=base)


def now_local() -> dt.datetime:
    return dt.datetime.now(config.CHINA_TZ)


def fmt_num(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:,}"
    return str(value)


def fmt_dec2(value) -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"{Decimal(str(value)):,.2f}"
    except Exception:  # noqa: BLE001 - 展示层容错，原样返回
        return str(value)
