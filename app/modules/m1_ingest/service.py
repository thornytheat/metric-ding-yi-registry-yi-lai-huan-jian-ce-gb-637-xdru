"""M1 编排：一次完整运行的入口。

顺序固定：采信 → 语法/诊断 → 依赖图 → 版本 → 账目 → 落库。
同一输入摘要（batch_key）重跑直接复用已完成批次，不新增行。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from ... import config, errors, manifest, reasons
from ..m3_diagnostics import metrics as diag_metrics
from ..m3_diagnostics import rules as diag_rules
from ..m3_diagnostics import service as diag_service
from ..m4_graph import service as graph_service
from ..m5_versions import service as version_service
from ..m6_impact import service as impact_service
from . import lines as lines_mod
from . import reader

DEFAULT_SAMPLE = "metrics_dirty.dsl"
CLEAN_SAMPLE = "metrics_clean.dsl"


def _now() -> str:
    return dt.datetime.now(config.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_sample(settings, name: str) -> tuple[str, str]:
    path = Path(settings.sample_dir) / name
    data = path.read_bytes()
    return data.decode("utf-8-sig"), manifest.digest_bytes(data)


def _stage(stage: str, in_count: int, out_count: int, isolated: int,
           note: str = "") -> dict:
    return {"stage": stage, "label": config.STAGE_LABELS[stage],
            "in_count": in_count, "out_count": out_count,
            "isolated": isolated, "note": note,
            "status": "done" if isolated == 0 else "done_with_quarantine"}


def run(settings, store, *, text: str | None = None,
        sample: str = DEFAULT_SAMPLE) -> dict:
    decoded, source_label = reader.read_source(
        Path(settings.sample_dir), text=text, name=sample)
    raw_rows, crlf_count = reader.split_lines(decoded.text)
    summary = lines_mod.summarize(raw_rows)
    empty_code = lines_mod.empty_state(summary)
    if empty_code and text is not None:
        raise errors.BadRequest(reasons.get(empty_code).title, code=empty_code,
                                detail={"lines": summary})
    if empty_code:
        raise errors.BadRequest(reasons.get(empty_code).title, code=empty_code,
                                detail={"lines": summary})

    versions_text, versions_digest = _read_sample(settings, "metric_versions.csv")
    reports_text, reports_digest = _read_sample(settings, "report_usage.csv")
    batch_key_value = manifest.batch_key(
        dsl_text=decoded.text, versions_digest=versions_digest,
        reports_digest=reports_digest, rule_version=settings.rule_version)

    existing = store.find_done_by_key(batch_key_value)
    if existing is not None:
        totals = store.load_totals(existing["batch_id"])
        return {
            "status": "done", "reused": True,
            "note": reasons.get("B_IDEMPOTENT_REPLAY").title,
            "batch": existing, "counters": totals,
            "accounts": store.load_totals(existing["batch_id"]).get("accounts_json", ""),
            "diagnostics": store.load_diagnostics(existing["batch_id"]),
        }

    started_at = _now()
    run_id = manifest.new_run_id()
    batch_id = manifest.digest_parts([batch_key_value, run_id])[:16]
    started = dt.datetime.now(config.UTC)

    # ---- 诊断 ----
    inspect = diag_service.inspect_lines(raw_rows)
    records = inspect["lines"]
    diagnostics: list[dict] = list(inspect["diagnostics"])

    # ---- 报表配置与依赖图 ----
    report_rows = graph_service.parse_reports_text(reports_text)
    graph = graph_service.analyse(inspect["metrics"], report_rows)
    diagnostics.extend(graph["diagnostics"])

    # ---- 版本 ----
    versions = version_service.load(settings, graph["metrics"])
    diagnostics.extend(versions["diagnostics"])

    diagnostics = diag_rules.ordered(diagnostics)
    isolated = diag_metrics.isolated_line_numbers(
        [d for d in diagnostics if d["stage"] in {"ingest", "diagnose"}])
    conflict_lines = sorted({c["other_line"] for c in graph["conflicts"]})
    isolated_set = sorted(set(isolated) | set(conflict_lines))
    for record in records:
        if record["line_no"] in conflict_lines:
            record["state"] = "isolated"
            record["code"] = next(
                (d["code"] for d in diagnostics if d.get("line_no") == record["line_no"]
                 and d["stage"] == "graph"), "C_DUP_NAME_BLOCK")

    # ---- 账目 ----
    accounts_result = impact_service.accounts(
        summary=summary, metrics=graph["metrics"], nodes=graph["nodes"],
        edges=graph["edges"], components=graph["components"],
        isolated_lines=len(isolated_set), reports=graph["reports"])
    totals = impact_service.totals_payload(accounts_result)
    totals["lines_total"] = str(summary["total"])

    # ---- 阶段计数 ----
    registered = len(graph["metrics"])
    version_rows = versions["rows"]
    version_bad = sum(1 for r in version_rows if r["status"] in {"OVERLAP", "INVERTED",
                                                               "BAD_FROM"})
    resolved_reports = sum(1 for r in graph["reports"] if r["resolved"])
    stages = [
        _stage("ingest", len(decoded.text.encode("utf-8")), summary["total"], 0,
               f"{decoded.encoding}"),
        _stage("syntax", summary["definition"], summary["definition"], 0,
               f"CRLF {crlf_count} 行"),
        _stage("diagnose", summary["definition"], registered,
               len(isolated_set), f"原因码 {len({d['code'] for d in diagnostics})} 种"),
        _stage("graph", registered, registered, len(graph["conflicts"]),
               f"节点 {len(graph['nodes'])} / 边 {len(graph['edges'])}"),
        _stage("version", len(version_rows), len(version_rows) - version_bad, version_bad,
               "[valid_from, valid_to)"),
        _stage("impact", registered, resolved_reports, len(graph["reports"]) - resolved_reports,
               f"环分量 {sum(1 for c in graph['components'] if c['is_cycle'])}"),
    ]
    finished_at = _now()
    elapsed_ms = int((dt.datetime.now(config.UTC) - started).total_seconds() * 1000)

    inputs = [
        {"name": source_label, "bytes": len(decoded.text.encode("utf-8")),
         "sha256": manifest.digest_text(decoded.text),
         "encoding": decoded.encoding, "bom_stripped": decoded.bom_stripped},
        {"name": "metric_versions.csv", "bytes": len(versions_text.encode("utf-8")),
         "sha256": versions_digest, "encoding": "utf-8", "bom_stripped": False},
        {"name": "report_usage.csv", "bytes": len(reports_text.encode("utf-8")),
         "sha256": reports_digest, "encoding": "utf-8", "bom_stripped": False},
    ]
    manifest_payload = manifest.build(
        run_id=run_id, batch_id=batch_id, batch_key_value=batch_key_value,
        settings=settings, source=source_label, inputs=inputs,
        params={"sample": sample, "text_supplied": text is not None,
                "crlf_lines": crlf_count},
        started_at=started_at, finished_at=finished_at, elapsed_ms=elapsed_ms,
        stages=stages,
        counters={"lines": summary["total"], "registered": registered,
                  "isolated": len(isolated_set),
                  "cycles": sum(1 for c in graph["components"] if c["is_cycle"])})

    batch = {
        "batch_id": batch_id, "batch_key": batch_key_value, "run_id": run_id,
        "source": source_label, "status": "done", "created_at": started_at,
        "finished_at": finished_at, "input_digest": batch_key_value,
        "note": "首次运行", "params": {"sample": sample},
    }
    store.save_run(batch=batch, payload={
        "lines": records,
        "metrics": graph["metrics"],
        "diagnostics": diagnostics,
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "components": graph["components"],
        "conflicts": graph["conflicts"],
        "versions": version_rows,
        "reports": graph["reports"],
        "totals": totals,
        "manifest": manifest_payload,
    })
    return {"status": "done", "reused": False, "batch": batch,
            "counters": totals, "stages": stages,
            "accounts": accounts_result, "diagnostics": diagnostics}
