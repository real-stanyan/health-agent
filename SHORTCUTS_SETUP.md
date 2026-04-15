# iPhone 快捷指令配置指南

目标：每天早上 8:00 自动从 Apple Health 读取关键指标，打包成 JSON，POST 到你 Mac 上的 `http://<Mac局域网IP>:8888/health`。

---

## 前置条件

1. iPhone 与 Mac **在同一 WiFi** 下。
2. Mac 已运行 `./run_server.sh`，终端会打印出 `本机局域网 IP`，记下来（例如 `192.168.1.23`）。
3. macOS 系统设置 → 网络 → 防火墙：如果开启，点「选项」把 Python / uvicorn 加到允许入站。

---

## 在 iPhone「快捷指令」App 里创建快捷指令

### Step 1：新建快捷指令
打开 **快捷指令 App** → 右上角「+」→ 命名为 **「同步 Apple Health」**。

### Step 2：依次添加以下动作

> 下面每一步都是「搜索动作 → 添加」。变量名可以点动作里的「默认变量」重命名，方便在最后拼 JSON 时引用。

#### 2.1 取心率（过去 24 小时）
- 动作：**查找健康样本**
  - 类型：`心率`
  - 排序：`开始日期（降序）`
  - 限制：`开启`，数量 `1000`
  - 开始日期：`过去 1 天`
- 动作：**获取健康样本的平均值** → 命名变量 **HR_AVG**
- 动作：**获取健康样本的最大值** → 命名变量 **HR_MAX**
- 动作：**获取健康样本的最小值** → 命名变量 **HR_MIN**

#### 2.2 静息心率
- 动作：**查找健康样本**
  - 类型：`静息心率`
  - 排序：`开始日期（降序）`，限制 1 条，范围 `过去 1 天`
- 动作：**获取健康样本的平均值** → **HR_RESTING**

#### 2.3 睡眠分析（昨晚）
- 动作：**查找健康样本**
  - 类型：`睡眠分析`
  - 范围：`过去 1 天`
- 用「计算」或「获取词典值」拆出：
  - 总睡眠小时数 → **SLEEP_TOTAL_H**
  - 深度睡眠小时数 → **SLEEP_DEEP_H**
  - REM 小时数 → **SLEEP_REM_H**
  - 中途醒来次数 → **SLEEP_AWAKE_TIMES**
  - 自评/iOS 睡眠评分 → **SLEEP_SCORE**（若无该字段，传 `null` 或 0）

> 提示：iOS 17+ 睡眠样本含 `inBed / asleep / deep / REM / awake`，用「重复遍历」+ 「增加到变量」分别累加时长（秒 → 小时：除以 3600）。

#### 2.4 体重（最近一次）
- 动作：**查找健康样本** → 类型：`体重`，排序 `开始日期（降序）`，限制 1 条
- 动作：**获取健康样本的详细信息**（数值）→ **WEIGHT_KG**

#### 2.5 主动能量消耗（今日）
- 动作：**查找健康样本** → 类型：`活动能量`，范围 `今天`
- 动作：**获取健康样本的总和** → **ACTIVE_KCAL**

#### 2.6 锻炼时间（今日）
- 动作：**查找健康样本** → 类型：`锻炼时间`，范围 `今天`
- 动作：**获取健康样本的总和**（分钟）→ **EXERCISE_MIN**

#### 2.7 步数（今日）
- 动作：**查找健康样本** → 类型：`步数`，范围 `今天`
- 动作：**获取健康样本的总和** → **STEPS**

#### 2.8 当前时间戳
- 动作：**当前日期** → 动作：**格式化日期**
  - 格式样式：`自定义`
  - 格式：`yyyy-MM-dd'T'HH:mm:ssXXX`
  - 时区：`Australia/Sydney`
- 命名变量 **TS**

### Step 3：拼 JSON

- 动作：**文本**（多行），内容：
```json
{
  "timestamp": "TS",
  "heart_rate": {
    "resting": HR_RESTING,
    "avg": HR_AVG,
    "max": HR_MAX,
    "min": HR_MIN
  },
  "sleep": {
    "total_hours": SLEEP_TOTAL_H,
    "deep_hours": SLEEP_DEEP_H,
    "rem_hours": SLEEP_REM_H,
    "awake_times": SLEEP_AWAKE_TIMES,
    "sleep_score": SLEEP_SCORE
  },
  "weight_kg": WEIGHT_KG,
  "active_energy_kcal": ACTIVE_KCAL,
  "exercise_minutes": EXERCISE_MIN,
  "steps": STEPS
}
```
把上面每一处大写变量名替换成前面动作里命名好的「魔法变量」。

### Step 4：POST 到 Mac

- 动作：**获取 URL 内容**
  - URL：`http://192.168.1.23:8888/health`（换成你 Mac 的实际 IP）
  - 方法：`POST`
  - 请求体：`文件` → 选上面那段 JSON 文本
  - Header：`Content-Type: application/json`

### Step 5：可选，弹个通知
- 动作：**显示通知** → 内容：`获取 URL 内容` 的结果，方便查错。

---

## 自动化：每天 8:00 自动运行

1. 快捷指令 App → 底部 **自动化** → 「新建个人自动化」
2. 触发条件：**特定时间** → `8:00` → 每日
3. 动作：**运行快捷指令** → 选「同步 Apple Health」
4. 关闭「运行前询问」

> iOS 15 之前需要手动点一次通知才会执行，iOS 15+ 支持全自动。

---

## 验证

1. 手动运行一次快捷指令。
2. Mac 上：`curl http://127.0.0.1:8888/latest` 看是否有新记录。
3. 跑一次 `./run_agent.sh`，查看 `reports/health_YYYY-MM-DD.md`。

---

## 故障排查

| 现象 | 排查 |
|---|---|
| iPhone 报「无法连接」 | Mac IP 是否变了（DHCP），同 WiFi 吗，防火墙放行 8888 了吗 |
| `{"detail":"invalid json"}` | JSON 文本里还有没替换的变量占位符；数值字段是否被当成字符串 |
| 睡眠总是 0 | 「睡眠分析」在 iOS 里需要你佩戴 Apple Watch 或手动录入 |
| 时间戳格式不对 | Step 2.8 的「格式化日期」必须选 `Australia/Sydney`，格式含 `XXX` 输出 `+11:00` |
