"""固定装置：临时库、固定评估日、真实样例目录、TestClient。

约定：时间断言只用 EVAL_DATE（2026-11-15），不读 datetime.now()。
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from app import config                                     # noqa: E402
from app.main import create_app                            # noqa: E402
from app.modules.m1_ingest import service as ingest        # noqa: E402
from app.store import Store                                # noqa: E402

EVAL_DATE = dt.date(2026, 11, 15)
SAMPLE_DIR = ROOT / "sample_data"
DIRTY = "metrics_dirty.dsl"
CLEAN = "metrics_clean.dsl"


@pytest.fixture()
def settings(tmp_path) -> config.Settings:
    return config.Settings(db_path=str(tmp_path / "metricreg.sqlite"),
                           sample_dir=str(SAMPLE_DIR),
                           eval_date=EVAL_DATE)


@pytest.fixture()
def store(settings) -> Store:
    return Store(settings.db_path)


@pytest.fixture()
def run(settings, store) -> dict:
    return ingest.run(settings, store)


@pytest.fixture()
def batch_id(run) -> str:
    return run["batch"]["batch_id"]


@pytest.fixture()
def clean_run(settings, store) -> dict:
    return ingest.run(settings, store, sample=CLEAN)


@pytest.fixture()
def app(settings):
    return create_app(settings)


@pytest.fixture()
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture()
def client_with_run(client) -> TestClient:
    response = client.post("/api/import", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "done"
    return client


@pytest.fixture()
def dirty_text() -> str:
    return (SAMPLE_DIR / DIRTY).read_text(encoding="utf-8-sig")


def sample_bytes(name: str = DIRTY) -> bytes:
    return (SAMPLE_DIR / name).read_bytes()


def codes(diags) -> list[str]:
    return [d["code"] for d in diags]
