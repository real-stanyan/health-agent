# Vercel + Upstash 部署指南

把接收端从 Mac 本地迁到公网，iPhone 不用再连家里 WiFi。

## 架构

```
iPhone Shortcut
    │  POST /health
    ▼
Vercel Serverless (api/index.py, FastAPI)
    │  RPUSH health:records
    ▼
Upstash Redis (List 存储 JSON 字符串)
    ▲
    │  GET /history
    │
Mac launchd / run_agent.sh  → 生成日报
```

## Step 1：生成鉴权 token

```bash
openssl rand -hex 32
```
复制输出，这是 `AUTH_TOKEN`。

## Step 2：部署到 Vercel

1. 先把 repo push 到 GitHub
2. https://vercel.com/new → Import 这个 repo
3. Framework Preset：**Other**，Root Directory：`./`
4. 展开 **Environment Variables**，先只加 1 条：
   - `AUTH_TOKEN` = 上一步生成的值
5. Deploy → 拿到 `https://xxx.vercel.app`

## Step 3：在 Vercel 里挂 KV（Upstash Redis）

Vercel 把存储放在 **Marketplace**，流程一键完成，不用单独去 Upstash 注册：

1. 进刚才部署的项目 → 顶部 **Storage** tab → **Create Database**
2. 选 **Upstash Redis**（Marketplace 会自动帮你开 Upstash 账号并链接）
3. Database Name: `health-agent`，Region 选离悉尼近的（Sydney / Singapore）
4. Create → 选中要连接的项目（当前这个）→ Connect
5. Vercel 会自动把 `KV_REST_API_URL` 和 `KV_REST_API_TOKEN` 注入到项目环境变量里
6. 回到 Deployments tab → 最新一次部署 → **Redeploy**（让新 env vars 生效）

## Step 4：验证（redeploy 完成后）

```bash
# 健康检查
curl https://xxx.vercel.app/

# 写一条
curl -X POST https://xxx.vercel.app/health \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: YOUR_AUTH_TOKEN" \
  -d '{"test": 1}'

# 读回来
curl https://xxx.vercel.app/latest \
  -H "X-Auth-Token: YOUR_AUTH_TOKEN"
```

## Step 5：改 iPhone Shortcut

打开「同步 Apple Health」Shortcut，找到 `Get Contents of URL` 动作：

- URL：`https://xxx.vercel.app/health`（之前的局域网 IP 作废）
- Method：POST
- Headers：
  - `Content-Type`: `application/json`
  - `X-Auth-Token`: `YOUR_AUTH_TOKEN`
- Request Body：保持不变

## Step 6：让本地 Agent 从 Vercel 拉数据

在项目根目录建 `.env.local`：
```
HEALTH_API_URL=https://xxx.vercel.app
AUTH_TOKEN=YOUR_AUTH_TOKEN
```

之后 `./run_agent.sh` 会自动走 HTTP，不再读 `health_data.json`。launchd 的 `.plist` 不用改（脚本会加载 .env.local）。

## 迁移已有本地数据（可选）

如果想把 `health_data.json` 里的历史数据搬上去：
```bash
python3 -c "
import json, os, urllib.request
url = os.environ['HEALTH_API_URL']
token = os.environ['AUTH_TOKEN']
records = json.load(open('health_data.json'))
for r in records:
    req = urllib.request.Request(
        f'{url}/health',
        data=json.dumps(r).encode(),
        headers={'Content-Type':'application/json', 'X-Auth-Token':token},
        method='POST',
    )
    print(json.loads(urllib.request.urlopen(req).read()))
"
```
