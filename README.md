# Apple Health 监控 Agent

本地 Agent：iPhone 快捷指令 → Mac FastAPI 收集 → Python Agent 分析 → Markdown 日报。

## 快速开始

```bash
cd ~/Github/health-agent

# 1. 装依赖（建议先建 venv）
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 启动收集服务（会打印你的 Mac 局域网 IP）
./run_server.sh

# 3. 配置 iPhone 快捷指令
# 按 SHORTCUTS_SETUP.md 操作，把 POST 目标填成 http://<Mac IP>:8888/health

# 4. 手动触发分析（或每天定时跑）
./run_agent.sh
# 日报生成在 reports/health_YYYY-MM-DD.md
```

## 目录

```
health-agent/
├── server.py              # FastAPI 服务（端口 8888）
├── health_agent.py        # 日报生成 Agent
├── health_data.json       # 数据存储（首次运行自动创建）
├── reports/               # Markdown 日报输出
├── requirements.txt
├── run_server.sh
├── run_agent.sh
└── SHORTCUTS_SETUP.md     # iPhone 配置说明
```

## 接口

| Method | Path | 说明 |
|---|---|---|
| POST | `/health` | 接收 iPhone 推送，追加到 `health_data.json` |
| GET | `/latest` | 最近一条记录 |
| GET | `/history` | 全部历史 |

## 定时运行日报（可选）

macOS 上用 `launchd` 或 `crontab`：

```bash
crontab -e
# 每天晚上 21:30 跑一次日报
30 21 * * * cd /Users/stanyan/Github/health-agent && /usr/bin/env bash run_agent.sh >> /tmp/health_agent.log 2>&1
```

## 时区
全部按 `Australia/Sydney` 处理。
# health-agent
