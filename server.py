"""Apple Health 本地代理服务：所有数据读写都走 Vercel API，不存本地。"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API_URL = os.environ.get("HEALTH_API_URL", "https://health-agent-alpha.vercel.app").rstrip("/")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "aed8fbf9fbb2cb44dfcb826c1b3d42091c272fe0869ac473a1d6ce9a6ec8fcd2")

app = FastAPI(title="Apple Health Monitor (proxy)", version="0.3.0")


def _proxy_get(path: str) -> Any:
    req = urllib.request.Request(f"{API_URL}{path}")
    if AUTH_TOKEN:
        req.add_header("X-Auth-Token", AUTH_TOKEN)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _proxy_post(path: str, body: dict) -> Any:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{API_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if AUTH_TOKEN:
        req.add_header("X-Auth-Token", AUTH_TOKEN)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


@app.post("/health")
async def ingest(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid json: {e}")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")
    return _proxy_post("/health", payload)


@app.get("/latest")
def latest() -> dict[str, Any]:
    return _proxy_get("/latest")


@app.get("/history")
def history() -> dict[str, Any]:
    return _proxy_get("/history")


@app.get("/dashboard")
def dashboard() -> FileResponse:
    return FileResponse(ROOT / "dashboard.html", media_type="text/html")


@app.get("/")
def root() -> dict[str, Any]:
    return {"service": "apple-health-monitor", "mode": "proxy", "upstream": API_URL,
            "endpoints": ["/health", "/latest", "/history", "/dashboard"]}
