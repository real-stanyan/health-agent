#!/usr/bin/env bash
# 启动 FastAPI 服务 & 打印局域网 IP
set -euo pipefail

cd "$(dirname "$0")"

# 虚拟环境（可选）：如果存在 .venv 就用它
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# 获取局域网 IP（macOS）
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")

echo "────────────────────────────────────────────"
echo "🩺  Apple Health Monitor Server"
echo "   本机局域网 IP : ${LAN_IP}"
echo "   快捷指令 POST 到: http://${LAN_IP}:8888/health"
echo "   调试: http://${LAN_IP}:8888/latest"
echo "────────────────────────────────────────────"

exec uvicorn server:app --host 0.0.0.0 --port 8888 --reload
