# boss-wxapp-autoapply

PC **微信小程序版 BOSS直聘** 的半自动求职系统：通过 **CDP/Frida 注入**驱动小程序——直接读渲染层 DOM 拿结构化职位数据、用 CDP 触摸事件点「立即沟通」投递。自动筛选 → 投递打招呼 → HR 回复巡检转人工。

> **架构演进**：早期用"截图 + VLM 定位 + SendInput"非侵入视觉控制，因**慢（~90s/卡）+ OCR 误差**已废弃。现核心改为 **CDP 注入**：读 DOM **精确、~30ms/屏**，点元素**精准、不抢前台、不截图**。设计与实测见 `.omc/plans/boss-wxapp-cdp-pivot.md`。
>
> 代价：Frida 注入微信 = 客户端篡改，有**封微信号风险** → **强烈建议用小号**。

---

## 架构

```
React 精简控制台（投递看板 / HR 收件箱 / 规则 / 日志 / 岗位流）
   │ REST · SSE                                ← localhost + 可选 token + Origin 鉴权
┌──▼───────────────────────────────────────────────────────────┐
│ FastAPI 后端 (Python, :8010)                                  │
│  pipeline（唯一投递权威）: collector → screener(硬过滤)        │
│                            → dispatcher(幂等状态机 + 限速)     │
│  automation/inbox_watcher 常驻巡检 → HR 回复转人工            │
│  pages/boss_wxapp.py  BossWxappDriver（CDP 实现）            │
│  cdp/client.py  同步 CDP 客户端（单例，连侧车 :62000）        │
└───────────────────────┬───────────────────────────────────────┘
                        │ CDP (WebSocket JSON)
┌───────────────────────▼───────────────────────────────────────┐
│ WMPFDebugger 侧车 (Node, :62000)  ← _tools/WMPFDebugger        │
│  Frida 注入 WeChatAppEx，私有调试协议 ⇄ 标准 Chrome DevTools  │
└───────────────────────┬───────────────────────────────────────┘
                        │ Frida 注入
                 PC 微信「BOSS直聘」小程序
```

**读 = 渲染层 DOM**：CDP 连小程序根帧，职位内容在同源子 `iframe`，经 `iframe.contentDocument` 直读（精确、零 OCR）。
**写 = `Input.dispatchTouchEvent`**：根视口坐标注入真实触摸触发小程序 `bindtap`（鼠标事件无效，必须触摸）。

---

## 前置要求

| 依赖 | 说明 |
|---|---|
| **Windows + PC 微信 4.x** | WMPF 运行时（`WeChatAppEx.exe`），实测微信 4.1.10 / WMPF **19921** |
| **Node.js ≥ 22** + corepack | 跑 WMPFDebugger 侧车 |
| **Python + uv** | 后端（mp 自带 venv，`uv sync`） |
| **pnpm** | 前端 |
| **MSVC 生成工具**（可选） | 仅当 frida 需源码构建时 |
| **代理**（中国大陆） | frida 预编译包从国外下载，装依赖时需要 |

---

## 一、部署小程序注入侧车（WMPFDebugger）★关键

这是整个系统的地基——它把微信小程序的私有调试协议转成标准 CDP，后端才能读/控小程序。

### 1. 获取
```bash
git clone https://github.com/evi0s/WMPFDebugger E:\TestProjects\_tools\WMPFDebugger
```

### 2. 确认你的 WMPF 版本受支持
任务管理器 → 找到 `WeChatAppEx.exe` → 右键「打开文件所在位置」→ 路径里 `RadiumWMPF\<数字>\extracted` 的 `<数字>` 即版本号。
确认该版本在 WMPFDebugger README 的支持列表里（如 **19921**）。不在 → 需按其 `ADAPTATION.md` 自行适配或提 issue。
> 升级到最新 WMPF：从 `pc.weixin.qq.com` 下最新微信安装包（WMPF 随包安装）。

### 3. 安装依赖
```powershell
cd E:\TestProjects\_tools\WMPFDebugger
# 中国大陆需走代理 + 中文 Windows 需 UTF-8 模式（否则 frida 安装会 GBK 解码报错）
$env:HTTP_PROXY="http://127.0.0.1:7890"; $env:HTTPS_PROXY="http://127.0.0.1:7890"
$env:PYTHONUTF8="1"; $env:NODE_TLS_REJECT_UNAUTHORIZED="0"
corepack yarn install        # 下载 frida 预编译二进制(~112MB)
```
> 装好后 `node -e "require('frida')"` 应无报错。frida 17.x 无 node22 预编译时会源码构建（需 cmake + 从 github 克隆 frida-gum/core），务必配好代理。

### 4. 运行（注入 + 起 CDP）
```powershell
cd E:\TestProjects\_tools\WMPFDebugger
npx ts-node src/index.ts
```
看到这三行才算成功：
```
[server] proxy server running on ws://localhost:62000
[frida] script loaded, WMPF version: 19921, pid: xxxxx
[frida] you can now open any miniapps
```

### 5. 打开/重开 BOSS 小程序
- 在 PC 微信里搜索打开「**BOSS直聘**」小程序。
- **侧车每次（重）启动后，必须把小程序关掉再重新打开**，它才会连上新调试器（否则后端 `Runtime` 调用超时）。
- 停在 **聊天 → 新职位** 子标签页（投递主采集源）。

---

## 二、后端（uv）

```powershell
cd E:\TestProjects\mp\backend
uv sync                                  # 创建 venv 装依赖
copy .env.example .env                   # GPT_API_KEY 为历史 LLM 字段，保留即可（配置校验需要；LLM 打分默认关）
uv run uvicorn app.main:asgi_app --host 127.0.0.1 --port 8010
```
配置/历史数据库在 `backend/data/boss_autoapply.db`（已 gitignore）。

## 三、前端（pnpm）

```powershell
pnpm -C E:\TestProjects\mp\frontend install
pnpm -C E:\TestProjects\mp\frontend dev   # http://localhost:5180
```

---

## 完整启动顺序（每次开机重来）

| # | 步骤 | 终端/动作 |
|---|---|---|
| 1 | PC 微信打开 BOSS 小程序 | 微信 |
| 2 | 起侧车注入 | 终端1：`cd _tools\WMPFDebugger; npx ts-node src/index.ts`（等三行就绪） |
| 3 | **重开** BOSS 小程序，停在 聊天→新职位 | 微信 |
| 4 | 起后端 | 终端2：`cd mp\backend; uv run uvicorn app.main:asgi_app --host 127.0.0.1 --port 8010` |
| 5 | 起前端 | 终端3：`pnpm -C mp\frontend dev` |
| 6 | 投递 | 浏览器 http://localhost:5180 → 点**启动**（只点一次） |

三个服务（侧车/后端/前端）各占一个终端、都要一直开着。

---

## 投递行为

- **新职位优先**：始终在「聊天 → 新职位」feed 里投，逐张 进详情 → 点立即沟通（BOSS 发你配置的默认招呼语）→ 返回 feed → 滚动出更多。
- **投尽后**：回顶 + 下拉刷新 + 巡检 + 歇 3 分钟等新岗推送（不空转、不切走）。
- **去重**：`继续沟通`(已投)→ 跳过不计配额；`jd_hash` 已采过 → 跳过。
- **巡检**：每 K 卡/定时扫消息，HR 回复转人工（系统不自动续聊）。

## 规则（前端「规则」页或 config 表）

| 字段 | 作用 |
|---|---|
| `salary_min_k` | 薪资下限（如 13 → 刷掉 <13K，会记"初筛淘汰"） |
| `daily_limit` | 每日投递上限 |
| `night_stop_start/end` | 夜停时段（默认 23:00–10:00，期间只巡检不投） |
| `interval_min/max_sec` | 卡间随机间隔（拟人防封） |
| `dedup_contacted` | 是否跳过已沟通过的 |
| `keywords_include/exclude`、`allowed_cities`、`company_scales` | 关键词/城市/规模过滤 |
| `llm_enabled` | LLM 打分（默认关，纯硬过滤） |

---

## 运维硬约束（踩过的坑）

1. **运行期只允许一个 CDP 客户端**：WMPFDebugger 代理对多会话叠加敏感，叠加会致 `Input` 域错路/挂起。后端 `get_cdp()` 单例规避——**调试时勿同时跑探针脚本**。
2. **重启侧车 ⟹ 必须重开小程序**（旧调试会话不自动回连）。
3. **全局代理（Clash 等）运行期建议关**，避免 WebSocket 抖动致小程序闪退（侧车日志 `Invalid WebSocket frame`）。
4. **小号专用**：Frida 注入有封微信号风险。
5. 后端 :8010、前端 :5180、CDP 代理 :62000——端口冲突先清。

## 故障排查

| 现象 | 处理 |
|---|---|
| 侧车 `version config not found: XXXXX` | WMPF 版本未适配，见上「确认版本」 |
| 后端起来但点启动不动 / `Runtime` 超时 | 小程序没连上调试器 → 重开小程序（侧车重启后必做） |
| 小程序闪退 / 无限加载 | 关全局代理；严格按"侧车→开小程序→连"的顺序 |
| 投递成功但招呼语记录像 HR 名字 | 已修（`_grab_greeting` 用「由你发起的沟通」锚点）；旧记录可批量更正 |
| frida 安装卡住/超时 | 配代理 + `PYTHONUTF8=1`，见侧车「安装依赖」 |

---

## 目录

```
mp/
├─ backend/app/
│  ├─ cdp/           CDP 客户端（连侧车）★新感知/动作层
│  ├─ pages/boss_wxapp.py   BossWxappDriver（CDP 实现）
│  ├─ pipeline/      collector / screener / dispatcher / rate_limiter / runner
│  ├─ automation/    inbox_watcher 巡检
│  ├─ api/ models.py rules.py security/ config.py db.py
│  ├─ desktop/ llm/  ⚠ 旧视觉/LLM 层（待清理，CDP 已不依赖）
│  └─ data/          SQLite（config + 投递历史，gitignore）
├─ frontend/         React 19 + Vite（:5180）
└─ .omc/plans/boss-wxapp-cdp-pivot.md   设计 + 实测记录
```

> 半自动边界：自动筛选 + 投递 + 打招呼；HR 回复转人工接管，系统不自动续聊。
