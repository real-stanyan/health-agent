"""Vercel Serverless entry for Apple Health ingestion.

Storage: Upstash Redis (REST API) — list key `health:records`, each item is JSON.
Auth: optional `X-Auth-Token` header matched against env `AUTH_TOKEN`.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Request

UPSTASH_URL = (
    os.environ.get("KV_REST_API_URL")
    or os.environ.get("UPSTASH_REDIS_REST_URL")
    or ""
).rstrip("/")
UPSTASH_TOKEN = (
    os.environ.get("KV_REST_API_TOKEN")
    or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    or ""
)
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")
TZ = ZoneInfo("Australia/Sydney")
KEY = "health:records"

app = FastAPI(title="Apple Health Monitor", version="0.2.0")


def _upstash(command: list[Any]) -> Any:
    if not UPSTASH_URL or not UPSTASH_TOKEN:
        raise HTTPException(500, "upstash env not configured")
    body = json.dumps(command).encode("utf-8")
    req = urllib.request.Request(
        UPSTASH_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {UPSTASH_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if "error" in payload:
        raise HTTPException(502, f"upstash error: {payload['error']}")
    return payload.get("result")


def _check_auth(token: str | None) -> None:
    if AUTH_TOKEN and token != AUTH_TOKEN:
        raise HTTPException(401, "unauthorized")


@app.post("/health")
async def ingest(request: Request, x_auth_token: str | None = Header(None)) -> dict[str, Any]:
    _check_auth(x_auth_token)
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"invalid json: {e}")
    if not isinstance(payload, dict):
        raise HTTPException(400, "payload must be a JSON object")

    if not payload.get("timestamp"):
        payload["timestamp"] = datetime.now(TZ).isoformat()
    payload["_received_at"] = datetime.now(TZ).isoformat()

    _upstash(["RPUSH", KEY, json.dumps(payload, ensure_ascii=False)])
    count = _upstash(["LLEN", KEY])
    return {"ok": True, "count": count, "timestamp": payload["timestamp"]}


@app.get("/latest")
def latest(x_auth_token: str | None = Header(None)) -> dict[str, Any]:
    _check_auth(x_auth_token)
    items = _upstash(["LRANGE", KEY, -1, -1]) or []
    record = json.loads(items[0]) if items else None
    return {"ok": True, "record": record}


@app.get("/history")
def history(x_auth_token: str | None = Header(None)) -> dict[str, Any]:
    _check_auth(x_auth_token)
    items = _upstash(["LRANGE", KEY, 0, -1]) or []
    records = [json.loads(r) for r in items]
    return {"ok": True, "count": len(records), "records": records}


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "apple-health-monitor",
        "version": "0.2.0",
        "endpoints": ["/health", "/latest", "/history"],
    }
