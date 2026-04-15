"""健康日报生成 Agent：读取最近 7 天数据，输出 Markdown 报告。"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dateutil import parser as dtparser


# ---- sleep_raw 解析 -------------------------------------------------

_STAGE_ALIASES = {
    "core": "core",
    "asleepcore": "core",
    "deep": "deep",
    "asleepdeep": "deep",
    "rem": "rem",
    "asleeprem": "rem",
    "awake": "awake",
    "inbed": "in_bed",
    "asleep": "asleep_generic",
    "asleepunspecified": "asleep_generic",
}

# 每行抽取所有 [...] 分组；第一项 = stage，最后一项 = duration
_BRACKET_RE = re.compile(r"\[([^\]]+)\]")


def _parse_duration_to_seconds(tok: str) -> int:
    parts = tok.split(":")
    if len(parts) == 1:
        return int(parts[0])
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0


def parse_sleep_raw(text: str) -> dict[str, float]:
    """把 iPhone 快捷指令导出的分段文本解析成 {stage: hours}。"""
    totals_s: dict[str, int] = {"core": 0, "deep": 0, "rem": 0, "awake": 0, "in_bed": 0, "asleep_generic": 0}
    for line in (text or "").splitlines():
        brackets = _BRACKET_RE.findall(line)
        if len(brackets) < 2:
            continue
        stage_raw, dur_raw = brackets[0], brackets[-1]
        key = _STAGE_ALIASES.get(stage_raw.strip().lower().replace(" ", ""))
        if not key:
            continue
        if not re.fullmatch(r"\d{1,2}(?::\d{2}){0,2}", dur_raw):
            continue
        totals_s[key] += _parse_duration_to_seconds(dur_raw)

    hours = {f"{k}_hours": round(v / 3600, 2) for k, v in totals_s.items()}
    asleep = totals_s["core"] + totals_s["deep"] + totals_s["rem"]
    hours["asleep_hours"] = round(asleep / 3600, 2)
    hours["total_hours"] = round((asleep + totals_s["awake"]) / 3600, 2)
    return hours


def enrich_sleep(record: dict[str, Any]) -> dict[str, Any]:
    """如果记录里有 sleep_raw，解析后注入到 record['sleep'] 字典。"""
    raw = record.get("sleep_raw")
    if not isinstance(raw, str) or not raw.strip():
        return record
    parsed = parse_sleep_raw(raw)
    sleep = dict(record.get("sleep") or {})
    for k, v in parsed.items():
        sleep.setdefault(k, v)
    record["sleep"] = sleep
    return record

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "health_data.json"
REPORTS_DIR = ROOT / "reports"
TZ = ZoneInfo("Australia/Sydney")

EXERCISE_KCAL_TARGET = 500


def load_records() -> list[dict[str, Any]]:
    api_url = os.environ.get("HEALTH_API_URL", "").rstrip("/")
    if api_url:
        req = urllib.request.Request(f"{api_url}/history")
        token = os.environ.get("AUTH_TOKEN")
        if token:
            req.add_header("X-Auth-Token", token)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("records", [])
    if not DATA_FILE.exists():
        return []
    with DATA_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def recent_window(records: list[dict[str, Any]], days: int = 7) -> list[dict[str, Any]]:
    now = datetime.now(TZ)
    cutoff = now - timedelta(days=days)
    out = []
    for r in records:
        ts = r.get("timestamp")
        if not ts:
            continue
        try:
            t = dtparser.parse(ts)
            if t.tzinfo is None:
                t = t.replace(tzinfo=TZ)
        except Exception:
            continue
        if t >= cutoff:
            enriched = enrich_sleep({**r})
            enriched["_parsed_ts"] = t
            out.append(enriched)
    out.sort(key=lambda r: r["_parsed_ts"])
    return out


def _get(r: dict[str, Any], *path: str, default: float | None = None):
    cur: Any = r
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur if cur is not None else default


def ascii_spark(values: list[float | None]) -> str:
    """一个极简的 ASCII sparkline。"""
    nums = [v for v in values if isinstance(v, (int, float))]
    if not nums:
        return "(无数据)"
    lo, hi = min(nums), max(nums)
    span = hi - lo or 1
    bars = "▁▂▃▄▅▆▇█"
    out = []
    for v in values:
        if not isinstance(v, (int, float)):
            out.append(" ")
            continue
        idx = int((v - lo) / span * (len(bars) - 1))
        out.append(bars[idx])
    return "".join(out)


def detect_anomalies(window: list[dict[str, Any]]) -> list[str]:
    alerts: list[str] = []
    if not window:
        return alerts

    latest = window[-1]
    resting = _get(latest, "heart_rate", "resting")
    if isinstance(resting, (int, float)):
        if resting > 100:
            alerts.append(f"⚠️ 静息心率偏高：{resting} bpm（> 100）")
        elif resting < 40:
            alerts.append(f"⚠️ 静息心率偏低：{resting} bpm（< 40）")

    sleep_hours = _get(latest, "sleep", "total_hours")
    if isinstance(sleep_hours, (int, float)) and sleep_hours < 6:
        alerts.append(f"😴 昨晚睡眠不足：{sleep_hours:.1f} 小时（< 6）")

    # 连续 3 天运动消耗 < 200
    last3 = window[-3:]
    if len(last3) >= 3:
        kcals = [_get(r, "active_energy_kcal") for r in last3]
        if all(isinstance(k, (int, float)) and k < 200 for k in kcals):
            alerts.append("🔥 连续 3 天主动能量消耗 < 200 kcal，运动量不足")

    # 体重 7 天变化 > 2kg
    weights = [_get(r, "weight_kg") for r in window if _get(r, "weight_kg") is not None]
    if len(weights) >= 2:
        delta = weights[-1] - weights[0]
        if abs(delta) > 2:
            direction = "上升" if delta > 0 else "下降"
            alerts.append(f"⚖️ 7 天内体重{direction} {abs(delta):.1f} kg（> 2 kg）")

    return alerts


def build_suggestions(window: list[dict[str, Any]]) -> list[str]:
    tips: list[str] = []
    if not window:
        return ["暂无数据，先让 iPhone 快捷指令跑一次吧。"]

    latest = window[-1]

    sleep_hours = _get(latest, "sleep", "total_hours")
    if isinstance(sleep_hours, (int, float)) and sleep_hours < 7:
        tips.append(f"睡眠 {sleep_hours:.1f}h 偏少，建议今晚提前 30 分钟上床。")

    kcals = [_get(r, "active_energy_kcal", default=0) or 0 for r in window]
    avg_kcal = sum(kcals) / len(kcals)
    if avg_kcal < EXERCISE_KCAL_TARGET:
        gap = EXERCISE_KCAL_TARGET - avg_kcal
        tips.append(f"7 天日均消耗 {avg_kcal:.0f} kcal，距离目标 {EXERCISE_KCAL_TARGET} 还差 {gap:.0f}，加一次 30 分钟快走。")

    steps = _get(latest, "steps")
    if isinstance(steps, (int, float)) and steps < 8000:
        tips.append(f"今日步数 {int(steps)}，通勤+午休各加 15 分钟步行可补到 8000+。")

    resting = _get(latest, "heart_rate", "resting")
    if isinstance(resting, (int, float)) and resting > 80:
        tips.append(f"静息心率 {resting} bpm 偏高，注意咖啡因摄入和压力管理。")

    if not tips:
        tips.append("各项指标稳定，保持当前节奏。")

    return tips[:3]


def fmt_value(v: Any, unit: str = "", precision: int = 1) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{precision}f}{unit}"
    return f"{v}{unit}"


def render_report(window: list[dict[str, Any]]) -> str:
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    lines: list[str] = []
    lines.append(f"# 健康日报 - {today}\n")

    if not window:
        lines.append("> 暂无最近 7 天的数据。请确认 iPhone 快捷指令是否正常推送。\n")
        return "\n".join(lines)

    latest = window[-1]
    lines.append("## 今日概况\n")
    lines.append(f"- 💓 心率：静息 {fmt_value(_get(latest, 'heart_rate', 'resting'), ' bpm', 0)}，"
                 f"均 {fmt_value(_get(latest, 'heart_rate', 'avg'), ' bpm', 0)}，"
                 f"峰 {fmt_value(_get(latest, 'heart_rate', 'max'), ' bpm', 0)}")
    lines.append(f"- 😴 睡眠：总 {fmt_value(_get(latest, 'sleep', 'total_hours'), ' h')}，"
                 f"深 {fmt_value(_get(latest, 'sleep', 'deep_hours'), ' h')}，"
                 f"REM {fmt_value(_get(latest, 'sleep', 'rem_hours'), ' h')}，"
                 f"评分 {fmt_value(_get(latest, 'sleep', 'sleep_score'), '', 0)}")
    lines.append(f"- ⚖️ 体重：{fmt_value(_get(latest, 'weight_kg'), ' kg')}")
    lines.append(f"- 🔥 运动：{fmt_value(_get(latest, 'active_energy_kcal'), ' kcal', 0)} / "
                 f"{fmt_value(_get(latest, 'exercise_minutes'), ' min', 0)} / "
                 f"{fmt_value(_get(latest, 'steps'), ' 步', 0)}")
    lines.append("")

    lines.append("## 趋势分析（近 7 天）\n")
    resting_series = [_get(r, "heart_rate", "resting") for r in window]
    sleep_series = [_get(r, "sleep", "sleep_score") for r in window]
    weight_series = [_get(r, "weight_kg") for r in window]
    kcal_series = [_get(r, "active_energy_kcal") for r in window]

    lines.append(f"- 静息心率：`{ascii_spark(resting_series)}`  {[v for v in resting_series]}")
    lines.append(f"- 睡眠评分：`{ascii_spark(sleep_series)}`  {[v for v in sleep_series]}")
    lines.append(f"- 体重 kg：  `{ascii_spark(weight_series)}`  {[v for v in weight_series]}")
    lines.append(f"- 能量 kcal：`{ascii_spark(kcal_series)}`  {[v for v in kcal_series]}")

    kcals = [v for v in kcal_series if isinstance(v, (int, float))]
    if kcals:
        rate = sum(1 for v in kcals if v >= EXERCISE_KCAL_TARGET) / len(kcals) * 100
        lines.append(f"- 能量目标（{EXERCISE_KCAL_TARGET} kcal）达成率：**{rate:.0f}%**")

    if len(weight_series) >= 2 and all(isinstance(v, (int, float)) for v in [weight_series[0], weight_series[-1]]):
        delta = weight_series[-1] - weight_series[0]
        lines.append(f"- 体重 7 天变化：**{delta:+.1f} kg**")

    lines.append("")

    alerts = detect_anomalies(window)
    lines.append("## 异常提醒\n")
    if alerts:
        for a in alerts:
            lines.append(f"- {a}")
    else:
        lines.append("- ✅ 无异常")
    lines.append("")

    lines.append("## 健康建议\n")
    for i, tip in enumerate(build_suggestions(window), 1):
        lines.append(f"{i}. {tip}")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    records = load_records()
    window = recent_window(records, days=7)
    report = render_report(window)

    REPORTS_DIR.mkdir(exist_ok=True)
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    out_path = REPORTS_DIR / f"health_{today}.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"✅ 日报已生成：{out_path}")
    print(f"   窗口内记录数：{len(window)}")


if __name__ == "__main__":
    main()
