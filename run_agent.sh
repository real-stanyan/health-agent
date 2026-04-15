#!/usr/bin/env bash
# 手动触发健康日报生成
set -euo pipefail

cd "$(dirname "$0")"

# 加载本地环境变量（HEALTH_API_URL / AUTH_TOKEN），如果存在
if [ -f ".env.local" ]; then
  # shellcheck disable=SC1091
  set -a; source .env.local; set +a
fi

if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python3 health_agent.py

TODAY=$(TZ=Australia/Sydney date +%F)
REPORT="reports/health_${TODAY}.md"
if [ -f "$REPORT" ]; then
  echo "📄 报告路径: $(pwd)/${REPORT}"
fi
