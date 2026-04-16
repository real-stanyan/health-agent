"""Apple Health 数据接收服务 (FastAPI)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "health_data.json"
TZ = ZoneInfo("Australia/Sydney")

app = FastAPI(title="Apple Health Monitor", version="0.1.0")


def _load() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        return []


def _save(records: list[dict[str, Any]]) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


@app.post("/health")
async def ingest(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid json: {e}")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")

    if "timestamp" not in payload or not payload["timestamp"]:
        payload["timestamp"] = datetime.now(TZ).isoformat()

    payload["_received_at"] = datetime.now(TZ).isoformat()

    # Shortcuts 隔天发送，Date 减一天还原为实际数据日期
    if "Date" in payload and payload["Date"]:
        try:
            # iOS Shortcuts 用 narrow no-break space (\u202f) 分隔时间和 am/pm
            date_str = payload["Date"].replace("\u202f", " ")
            dt = datetime.strptime(date_str, "%d %b %Y at %I:%M %p")
            dt -= timedelta(days=1)
            payload["Date"] = dt.strftime("%-d %b %Y at %-I:%M %p").replace("AM", "am").replace("PM", "pm")
        except ValueError:
            pass  # 格式不匹配则保持原值

    records = _load()
    records.append(payload)
    _save(records)

    return {"ok": True, "count": len(records), "timestamp": payload["timestamp"]}


@app.get("/latest")
def latest() -> dict[str, Any]:
    records = _load()
    if not records:
        return {"ok": True, "record": None}
    return {"ok": True, "record": records[-1]}


@app.get("/history")
def history() -> dict[str, Any]:
    records = _load()
    return {"ok": True, "count": len(records), "records": records}


@app.get("/dashboard")
def dashboard() -> FileResponse:
    return FileResponse(ROOT / "dashboard.html", media_type="text/html")


@app.get("/")
def root() -> dict[str, Any]:
    return {"service": "apple-health-monitor", "endpoints": ["/health", "/latest", "/history", "/dashboard"]}
