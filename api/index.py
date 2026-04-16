"""Vercel Serverless entry for Apple Health ingestion.

Storage: Upstash Redis (REST API) — list key `health:records`, each item is JSON.
Auth: optional `X-Auth-Token` header matched against env `AUTH_TOKEN`.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from dateutil import parser as dtparser
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
KEY = "health:daily"  # Redis Hash: field=YYYY-MM-DD, value=merged JSON

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


def _to_number(s: Any) -> Any:
    """把 '123' / '88.33' 转成 int / float；转不动原样返回。"""
    if isinstance(s, (int, float)) or not isinstance(s, str):
        return s
    try:
        f = float(s)
        return int(f) if f.is_integer() else round(f, 2)
    except ValueError:
        return s


def _normalize_numeric_lists(obj: Any) -> Any:
    """递归把所有「全是数字字符串」的 list 转成数字 list，顺带规范嵌套 dict。"""
    if isinstance(obj, dict):
        return {k: _normalize_numeric_lists(v) for k, v in obj.items()}
    if isinstance(obj, list):
        converted = [_to_number(x) if isinstance(x, str) else _normalize_numeric_lists(x) for x in obj]
        return converted
    return obj


def _derive_date(payload: dict[str, Any]) -> str:
    """从 payload 推 YYYY-MM-DD：优先 Date 字段，其次 timestamp，最后用服务器当日。"""
    raw = payload.get("Date") or payload.get("date") or payload.get("timestamp")
    if raw:
        try:
            dt = dtparser.parse(str(raw), fuzzy=True)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            return dt.astimezone(TZ).strftime("%Y-%m-%d")
        except Exception:
            pass
    return datetime.now(TZ).strftime("%Y-%m-%d")


@app.post("/health")
async def ingest(request: Request, x_auth_token: str | None = Header(None)) -> dict[str, Any]:
    _check_auth(x_auth_token)
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"invalid json: {e}")
    if not isinstance(payload, dict):
        raise HTTPException(400, "payload must be a JSON object")

    print(f"[POST /health] body={json.dumps(payload, ensure_ascii=False)}", flush=True)

    payload = _normalize_numeric_lists(payload)

    day = _derive_date(payload)
    payload["date"] = day
    # 洗掉 Shortcut 传来的带时分的 "16 Apr 2026 at 10:25 am"，统一成 "16/04/2026"
    try:
        payload["Date"] = dtparser.parse(day).strftime("%d/%m/%Y")
    except Exception:
        payload.pop("Date", None)
    if not payload.get("timestamp"):
        payload["timestamp"] = datetime.now(TZ).isoformat()
    payload["_received_at"] = datetime.now(TZ).isoformat()

    # 合并：读当日已有记录 → 浅合并 → 写回
    existing_raw = _upstash(["HGET", KEY, day])
    merged = json.loads(existing_raw) if existing_raw else {}
    merged.update(payload)

    _upstash(["HSET", KEY, day, json.dumps(merged, ensure_ascii=False)])
    total_days = _upstash(["HLEN", KEY])
    return {"ok": True, "date": day, "days_total": total_days, "fields": sorted(merged.keys())}


def _load_all_sorted() -> list[dict[str, Any]]:
    raw = _upstash(["HGETALL", KEY]) or []
    # Upstash HGETALL returns [field1, value1, field2, value2, ...]
    pairs = [(raw[i], raw[i + 1]) for i in range(0, len(raw), 2)]
    records = []
    for day, value in pairs:
        try:
            r = json.loads(value)
        except Exception:
            continue
        r.setdefault("date", day)
        records.append(r)
    records.sort(key=lambda r: r.get("date", ""))
    return records


@app.get("/latest")
def latest(x_auth_token: str | None = Header(None)) -> dict[str, Any]:
    _check_auth(x_auth_token)
    records = _load_all_sorted()
    return {"ok": True, "record": records[-1] if records else None}


@app.get("/history")
def history(x_auth_token: str | None = Header(None)) -> dict[str, Any]:
    _check_auth(x_auth_token)
    records = _load_all_sorted()
    return {"ok": True, "count": len(records), "records": records}


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "apple-health-monitor",
        "version": "0.2.0",
        "endpoints": ["/health", "/latest", "/history"],
    }
