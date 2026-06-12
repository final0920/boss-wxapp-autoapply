# 工作计划：boss-wxapp-autoapply —— PC 微信小程序版 BOSS直聘 半自动投递

**状态**: `pending approval`（本计划不会自动执行，待你批准执行路径）
**生成方式**: `/oh-my-claudecode:plan`（interview → direct）
**日期**: 2026-06-12（v2：执行层由 CDP 改为**非侵入视觉**）
**派生自**: `E:\TestProjects\ms`（安卓真机版 boss-autoapply）
**目标仓库**: `boss-wxapp-autoapply`；本地目录建议 `E:\TestProjects\mp`
**G0 闸门**: ✅ 已实测通过（2026-06-12，三探针全绿，见 §2.5）

---

## 1. 需求摘要

把 `ms` 的"自动筛选 + 半自动投递 + HR 巡检转人工"整条流程**原样保留**，仅把**执行层**从
"adb 控制已 root 安卓真机里的 BOSS直聘 App"替换为"**非侵入式控制 PC 微信小程序版 BOSS直聘**"。

### 已确认决策

| 维度 | 决策 | 含义 |
|---|---|---|
| 控制方式 | **视觉主（截图 + gpt-5.5 多模态 + SendInput），零注入** | `PrintWindow`/截图读小程序窗口像素 → VLM 定位 → `SendInput` 模拟鼠标键盘；全程不碰微信进程，微信号风险≈0 |
| 控制台范围 | **精简版 + 窗口预览** | 保留 投递看板/HR收件箱/规则/日志/岗位流/设置；去 scrcpy 投屏与 adb 终端；新增小程序窗口截图预览 |
| 代码关系 | **复制 ms → 新仓库替换执行层** | 拷贝整套核心，只换 `adb/` + `pages/boss.py` + `scrcpy/`；两项目独立演进 |

> **CDP/DOM 路线不废弃但降级**：已实测确认其对本机 WMPF 19921 现成可用（WMPFDebugger 支持列表首项即 19921），
> 但需注入微信、有微信号风险。列为 **Follow-up 可选后端**——将来嫌视觉烧 token，再加结构化后端省成本。

---

## 2. 环境事实（本机只读侦察坐实，2026-06-12）

| 项 | 实测值 | 对视觉路线的意义 |
|---|---|---|
| 微信主体 | Weixin 4.x，二进制 `D:\WeiXin\4.1.10.31`，注册版本 `4065597983` | 小程序窗口为其子进程所有 |
| 小程序运行时 | `WeChatAppEx.exe`（`RadiumWMPF\19921`），**Chromium 多进程内核** | 窗口是 Chromium GPU 加速窗口 → 捕获方式需验证（见 R1） |
| **显示缩放** | 进程命令行 `--device-scale-factor=1.5` | **DPI 150%**，截图坐标↔屏幕坐标映射必须 DPI-aware（见 R2/G0③） |
| 工具链 | node/npm/git/pnpm 齐全（视觉路线**不需要** node，仅备用） | Python 侧足够 |
| CDP 可行性 | 引擎带 `--remote-debugging-port`；WMPFDebugger 适配 19921 | 仅作 Follow-up 备选，本期不用 |

---

## 2.5 G0 验证结果（2026-06-12 实测，全部通过 ✅）

非侵入视觉路线已在真实 BOSS直聘小程序上端到端跑通，三探针全绿：

| 探针 | 结果 | 实测证据 |
|---|---|---|
| ① 窗口捕获 | ✅ | 找窗口 = WeChatAppEx 进程拥有的可见 `Chrome_WidgetWin_0`（643x1181）；**置顶 + 屏幕 DC BitBlt** 出清晰图（148KB，9000+色）；PrintWindow flag=2 置顶后亦可。纯像素读取，**零注入** |
| ② VLM 抽取 | ✅ | gpt-5.5 多模态正确抽出列表 3 张卡（职位/公司/薪资/地点 + 归一化坐标）；详情页字段（标题/薪资/地点/经验/学历/HR/JD/技能标签）齐全可读 |
| ③ SendInput 命中 | ✅ | 归一化坐标按 DPI 1.5 映射→物理像素→`mouse_event` 点击；点"标题行"成功进入**职位详情页**（含「立即沟通」按钮） |

**三条必须落进实现的硬性发现：**

1. **LLM 必须 httpx 直连，禁用 openai SDK**：SDK 的 `X-Stainless-*` 头/`OpenAI-Python` UA 被 gpt.pkpp.cn 前的 **Cloudflare WAF** 拦（403 "Your request was blocked."）；同请求 httpx 裸 POST → 200。→ 新项目 `llm/client.py` 用 httpx 重写（保留重试，偶发 502）。
2. **推理档位分级**：`reasoning_effort=high` 单次视觉调用 ~89s 太慢；视觉定位/抽取用 `low`（坐标质量无损、快很多），`high` 只留给 screener 文本打分。
3. **点位策略**：点卡片**几何中心会落在技能标签/HR 行（不跳转）**；要点**标题/薪资区**才进详情，投递点「立即沟通」按钮。→ VLM prompt 应直接返回"可点击进入详情/沟通的目标坐标"，而非卡片几何中心。

**坐标映射公式（已验证，PerMonitorV2 DPI-aware）**：`screen_px = 窗口左上(x,y) + 归一化/1000 × 窗口物理尺寸(w,h)`。
**捕获要点**：捕获前 `SetForegroundWindow` 触发小程序重绘（后台 GPU 窗口直接 PrintWindow 会返回空白）；投递期窗口需前台（已知代价）。

---

## 3. 复用 vs 重写（文件级映射）

### 3.1 后端（`ms/backend/app/`）

**几乎原样复用（决策权威 + 数据 + 编排，平台无关）**

| 文件 | 复用理由 | 改动 |
|---|---|---|
| `pipeline/runner.py` | 主循环只通过 `driver` 调设备；`runner.py:212` 才 `from app.pages.boss import BossDriver` | **仅改 1 处导入**为新 driver |
| `pipeline/dispatcher.py` | 幂等状态机；唯一设备调用是 `driver.tap_chat_and_capture`（`dispatcher.py:136`） | 0（契约不变） |
| `pipeline/screener.py` `collector.py` | LLM 打分 / 去重，纯逻辑 | 0；字段映射按小程序重标定 |
| `pipeline/rate_limiter.py` | 投递配额/限速 | 复用；**新增 VLM 调用预算/节流**（视觉每步烧 token，见 R4） |
| `automation/inbox_watcher.py` | 只调 `driver.open_message_tab/scrape_conversations/back_to_job_tab`（`inbox_watcher.py:66-74`） | 0（契约不变） |
| `models.py` `db.py` `rules.py` `notify.py` | SQLite/状态机/规则/通知 | 0 |
| `llm/client.py` `llm/prompts.py` | gpt-5.5 文本+**多模态**（视觉路线下多模态成主力） | 小增视觉 prompt |
| `security/auth.py` | localhost+token+Origin，控制台仍需 | 0 |
| `config.py` | pydantic-settings | 去 adb 项；加 窗口/坐标/VLM 预算项（§5） |
| `api/{applications,jobs,messages,config_api,logs,pipeline}.py` | REST，平台无关 | 0 |
| `main.py` | FastAPI+SocketIO ASGI 装配 | 去 scrcpy 命名空间注册（`main.py:159`） |

**必须重写（执行层 = 唯一平台耦合）**

| 原 | 新 | 工作 |
|---|---|---|
| `adb/`（tap/swipe/screencap…） | `desktop/`：`window.py`（找/置顶 BOSS 小程序窗口）、`capture.py`（PrintWindow/Graphics Capture 截图）、`input.py`（SendInput 鼠标键盘 + DPI 坐标映射） | 大 |
| `pages/boss.py`（`BossDriver`，控件树 resource-id + root input） | `pages/boss_wxapp.py`（`BossWxappDriver`，**截图→VLM 抽取/定位→SendInput**，同契约） | 大（含 VLM prompt 调优） |
| `scrcpy/`（安卓投屏） | 删除；预览改"窗口截图"端点 | 删 + 小 |
| `api/devices.py`（adb 设备） | `api/session.py`：微信客户端/小程序窗口在线状态 | 中 |
| `api/media.py`（adb 截图） | 窗口截图（capture.py） | 小 |

### 3.2 前端（`ms/frontend/src/`）

| 资源 | 处置 |
|---|---|
| 路由 `applications.tsx` `inbox.tsx` `logs.tsx` `rules.tsx` `settings.tsx` `index.tsx` `__root.tsx` | **复用** |
| 路由 `screen.tsx`（scrcpy 投屏+手动操控） | **替换**为窗口截图预览页（轮询/SSE 推图；可加"置顶小程序"按钮） |
| 组件 `ApplicationBoard` `InboxPanel` `RuleConfigForm` `ThemeToggle` `ui/*` | 复用 |
| 组件 `ScrcpyPlayer.tsx` | 删除，换 `<img>` 预览组件 |
| 组件 `DeviceSidebar` `lib/device-context.tsx` | 改造为"微信客户端/小程序会话"状态侧栏 |
| `lib/{i18n,socket,sse,utils}.ts` `api.ts` | 复用 |
| 依赖 `@yume-chan/scrcpy*` `@xterm/*` | **移除** |

---

## 4. 驱动契约（the seam —— 新 `BossWxappDriver` 必须实现，与 ms 完全一致）

runner/dispatcher/inbox_watcher 仅依赖以下方法（签名取自 `ms` 现有调用点）。**视觉实现下契约不变**：

| 方法 | 安卓实现（旧） | 小程序实现（新，视觉） |
|---|---|---|
| `prepare_device()` | 唤醒+解锁+重启 App | 找到/置顶 BOSS 小程序窗口，确保停在职位列表（锚点） |
| `detect_verify() -> bool` | 前台 activity 含 captcha | 截图 VLM 判定是否验证码/风控页 |
| `ensure_on_list() -> bool` | 回 MainActivity | VLM 识别当前页，非列表则点返回/重进 |
| `scrape_page() -> list[JobCard]` | uiautomator dump 解析卡片 | 截图 → VLM 抽取卡片 → RawJob + 点击坐标 |
| `scroll_list()` | root swipe | SendInput 滚轮/拖拽滚动列表 |
| `_tap_until(target)` / 开详情 | tap 后轮询 activity | SendInput 点击后截图 VLM 确认页面切换 |
| `dump() -> snapshot` | root `uiautomator dump` XML | **截图（+可选 VLM 结构化结果）作为页面快照** |
| `read_chat_button_label(detail) -> str` | 读 `btn_chat` 文案 | VLM 读"立即沟通/继续沟通"按钮文字 |
| `scrape_detail_fields(detail) -> dict` | 详情 resource-id | VLM 从详情截图抽字段 |
| `back_to_list()` | 逐层返回/兜底重启 | SendInput 点返回 / 兜底重进小程序 |
| `tap_chat_and_capture() -> (ok, greeting, reason)` | 点沟通→验证聊天页→抓招呼语（**投递动作**） | 点沟通→VLM 确认进会话→VLM 抓实发招呼语 |
| `open_message_tab()` / `back_to_job_tab()` / `scrape_conversations() -> list[dict]` | 切消息 tab + 解析会话 | 点消息入口 + VLM 解析会话列表 |

> 数据契约 `RawJob`（`collector.py:21`）字段不变：title/company/salary/area/jd/degree/experience/
> company_scale/finance_stage/hr_name/hr_active —— 新 driver 用 VLM 填这些字段即无缝接入 screener。
> **视觉优势**：靠语义识别字段/按钮，比硬选择器**更抗小程序改版**。

---

## 5. 视觉技术方案与关键陷阱

### 5.1 窗口捕获（观测）
- 找窗口：枚举 `WeChatAppEx.exe` 渲染进程拥有的顶层窗口，按标题/类名匹配 BOSS 小程序窗口（句柄）。
- 截图首选 **`PrintWindow(hwnd, PW_RENDERFULLCONTENT)`**：可后台/被遮挡仍出图；
  **但 Chromium GPU 加速窗口可能返回黑屏（R1）** → 兜底 **Windows.Graphics.Capture** 或"置顶 + `mss` 屏幕区域截图"。
- G0 必须实测三种捕获哪种在本机出图。

### 5.2 VLM 抽取/定位（决策仍在 pipeline，VLM 只做"看图说坐标"）
- 截图 → gpt-5.5 多模态 → 返回 0-1000 归一化坐标 + 结构化字段（沿用 ms vision_backend 的坐标范式）。
- 列表卡片/详情字段/按钮位置由 VLM 输出；screener 字段从 VLM 结构化结果取。

### 5.3 模拟输入（SendInput）
- 坐标映射：VLM 归一化坐标 → 窗口客户区像素 → 屏幕物理像素，**必须按 DPI 1.5 换算**（R2）；进程设 `SetProcessDpiAwareness(PER_MONITOR)`。
- 点击/滚动/输入走 **`SendInput`**（绝对坐标 0-65535 或物理坐标）；**需窗口前台可见**（R3）。
- 中文输入（如需）走剪贴板粘贴或 SendInput Unicode；BOSS"自动打招呼"多数免输入。

### 5.4 截图预览
- 复用 capture.py 出 PNG → `/api/media` 端点 → 前端预览页。

---

## 6. 实施步骤（里程碑）

### M0 — 仓库与骨架
1. 复制 `ms` → `mp/`，删 `adb/` `scrcpy/` `pages/boss.py` 与前端 scrcpy/xterm 相关。
2. `pyproject.toml`：去 `uiautomator2`；加 `pywin32`（PrintWindow/SendInput/窗口枚举）、`mss`、`Pillow`（保留）、`openai`/`httpx`（保留）。
3. `config.py`：去 adb 项；加 `MINIPROGRAM_WINDOW_TITLE`、`CAPTURE_BACKEND`、`DPI_SCALE`、`VLM_DAILY_BUDGET`。

### M0.5 — **G0 可行性闸门（go/no-go，非侵入，前置硬门）**
4. `mp/backend/scripts/probe_vision.py` 实测三探针（零注入）：
   - ① **窗口捕获**：定位 BOSS 小程序窗口 + 三种捕获法择一出清晰图（解决 R1 黑屏）；
   - ② **VLM 抽取命中**：gpt-5.5 从列表/详情截图抽 职位卡/字段/按钮坐标的命中率与单步成本；
   - ③ **SendInput 命中**：按 DPI 1.5 映射后点击职位卡，能否真正触发小程序跳转。
5. 闸门：①+③ 必过；②命中率<阈值 → 优化 prompt/裁剪截图，仍不达标则复议。

### M1 — 执行层骨架（`desktop/` + driver 骨架）
6. `desktop/window.py`（枚举/匹配/置顶窗口、客户区 rect）、`capture.py`（三捕获法 + DPI）、`input.py`（SendInput + 坐标映射）。
7. `pages/boss_wxapp.py` 骨架：`prepare_device/ensure_on_list/dump/detect_verify` 先通。

### M2 — 列表/详情/投递（对齐 runner 主循环）
8. `scrape_page/scroll_list/_tap_until/scrape_detail_fields/read_chat_button_label`：VLM prompt + 坐标落地。
9. `tap_chat_and_capture`（投递动作）：点沟通→VLM 确认会话→抓招呼语，回写 dispatcher 状态机（`dispatcher.py:136` 契约）。

### M3 — HR 巡检
10. `open_message_tab/scrape_conversations/back_to_job_tab`：VLM 解析消息页 → 对接 `inbox_watcher.poll_once`（零改）。

### M4 — 精简控制台
11. 前端：留 看板/收件箱/规则/日志/岗位流/设置；`screen.tsx`→窗口截图预览；`DeviceSidebar`→会话状态；移除 scrcpy/xterm。
12. 后端：`api/session.py`（窗口在线状态）、`api/media.py` 改窗口截图。

### M5 — 健壮性与反风控
13. 验证码/风控→PAUSED 通知；拟人化间隔+夜停+每日配额（沿用 `rate_limiter`，按小程序限额重标定）；
    窗口失焦/被切走自愈（重置前台→重截图）；**VLM 预算熔断**（R4）；可观测（RunLog 含 VLM 计数/捕获法/暂停原因，不记 key）。

---

## 7. 验收标准（可测试）

| # | 标准 | 指标 |
|---|---|---|
| AC1 | 窗口捕获 | 定位到 BOSS 小程序窗口；三捕获法至少一种出清晰非黑图，单帧<1s |
| AC2 | VLM 抽取 | 列表一屏≥10 卡，关键字段（title/company/salary/area + 经验/学历）完整率≥85% |
| AC3 | SendInput 命中 | DPI 1.5 映射后点卡进详情、点「立即沟通」进会话，成功率≥90%（G0 已先证伪） |
| AC4 | 投递动作 | score≥阈值自动沟通+招呼；`tap_chat_and_capture` 返回正确 (ok,greeting)；招呼语存证 |
| AC5 | LLM 筛选 | 沿用 ms screener，标注集 precision≥0.8、recall≥0.7 |
| AC6 | 投递幂等 | 崩溃中途不二次发送（dispatcher 只取 CLAIMED + 启动自检 `scan_sending`，`dispatcher.py:58`） |
| AC7 | HR 巡检 | 每 2–5min 巡检；新回复一周期内落 Message+RunLog 并 SSE 推前端；不自动回复 |
| AC8 | 限速拟人化 | 每日≤上限；间隔随机；夜停；验证码→PAUSED |
| AC9 | 锚点自愈 | 上轮卡详情/会话/弹层或窗口失焦，下轮 `ensure_on_list` 拉回列表 |
| AC10 | 精简控制台 | 看板/收件箱/规则/日志/岗位流/设置可用；窗口预览出图；接管置 `taken_over` |
| AC11 | 安全/密钥 | `.env` 不入库/日志/前端；缺 `GPT_API_KEY` 启动报错（`config.py:43`）；控制端点 token+localhost+Origin |
| AC12 | **VLM 预算** | 每日 VLM 调用计数+成本熔断；超额告警/降级；不记 key |
| AC13 | G0 闸门 | 产出 捕获法 + VLM 命中/成本 + SendInput 命中 三项报告 + go/no-go |

---

## 8. 目录结构（规划，`mp/`）

```
mp/
├─ backend/
│  ├─ pyproject.toml / .env.example
│  ├─ app/
│  │  ├─ main.py（去 scrcpy 注册）config.py（窗口/DPI/VLM 预算）db.py models.py rules.py notify.py
│  │  ├─ security/auth.py
│  │  ├─ desktop/        ★新：window.py / capture.py / input.py / __init__.py
│  │  ├─ pages/boss_wxapp.py   ★新：BossWxappDriver（截图+VLM+SendInput，同契约）
│  │  ├─ pipeline/ collector screener dispatcher rate_limiter(+VLM预算) runner（改 1 导入）
│  │  ├─ automation/ inbox_watcher.py（0 改）
│  │  ├─ llm/ client.py prompts.py(+视觉 prompt)
│  │  └─ api/ session.py（替 devices）media.py（窗口截图）applications jobs messages config_api logs pipeline
│  └─ scripts/probe_vision.py   ★新：G0 三探针（非侵入）
└─ frontend/  src/{routes(去 screen 投屏改预览),components(去 Scrcpy/xterm),lib,api.ts}
```

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| ~~R1 PrintWindow 黑屏~~ | ✅ **已解决（§2.5）**：置顶 + 屏幕 DC BitBlt 出清晰图（148KB/9000+色）；后台 GPU 窗口须先 SetForegroundWindow 触发重绘 |
| **R10 openai SDK 被 Cloudflare WAF 拦** | ✅ 已定位：`llm/client.py` 用 httpx 直连（剥 X-Stainless 头），不用 SDK；带重试兜偶发 502 |
| **R11 高推理视觉调用太慢(~89s)** | 视觉定位/抽取用 `reasoning_effort=low`；`high` 仅 screener 文本打分 |
| **R12 点卡片中心不跳转** | VLM 返回标题/薪资/「立即沟通」目标坐标，非几何中心 |
| **R2 DPI 1.5 坐标映射错位** | 进程 DPI-aware；归一化→客户区→物理像素显式换算；G0 用一次实点标定 |
| **R3 SendInput 需前台、占用机器** | 投递时独占前台（专机/小号专用）；探索 PostMessage 后台点击（Chromium 多不响应，仅备选）；失焦自愈 |
| **R4 VLM 每步 token 成本/延迟** | 截图区域裁剪、结果缓存、`rate_limiter` 加 VLM 预算熔断（AC12）；列表用一次截图批量抽多卡 |
| R5 小程序 UI≠App，字段位置变 | VLM 语义识别，**比硬选择器更抗改版**（视觉优势）；prompt 固化关键锚点 |
| R6 BOSS 账号风控/限额 | 限速/夜停/单账号沿用（行为层，与驱动方式无关）；验证码→PAUSED |
| R7 微信窗口被用户切走/最小化 | prepare/ensure 阶段置顶+校验；运行期监测前台窗口，丢失则暂停或重置 |
| R8 程序化打开小程序 | MVP floor：用户手开一次 → driver 仅置顶；后续探 weixin scheme 深链 |
| ~~注入/版本脆弱/微信号封禁~~ | **视觉路线零注入 → 该类风险消除；微信号风险≈0** |

---

## 10. 验证步骤

- **G0（前置，非侵入）**：`probe_vision.py` 三探针 go/no-go（AC1/AC3/AC13）。
- **单元**：VLM 结构化输出→RawJob 映射；坐标 DPI 换算；dispatcher 状态机（复用 ms 测试）；rate_limiter + VLM 预算；screener 回归。
- **集成**：端到端单岗位（截图→VLM 抽取→screen→沟通→SENT→巡检→通知）；崩溃注入不二次发送（`scan_sending`）。
- **控制台**：看板/收件箱/规则/日志冒烟；窗口预览出图；接管联动 `taken_over`。
- **健壮性**：窗口失焦自愈；验证码→PAUSED；夜停/配额；VLM 熔断。

---

## 11. 开放问题 / 后续

- N1：本机三种**窗口捕获法**哪种对 Chromium GPU 窗口出图（G0 第一优先）。
- N2：BOSS小程序「自动打招呼」是否进会话即视为投递成功（决定 `tap_chat_and_capture` 判据）。
- N3：聊天/搜索是否需要文字输入（决定 SendInput 文本/剪贴板方案）。
- N4：小程序每日沟通/投递限额实测（重标定 `daily_limit`/间隔）。
- N5：程序化打开小程序（weixin scheme / UI 自动化），MVP 先手动开。
- N6（Follow-up）：将来加 **CDP/DOM 结构化后端**省 token（已确认对 WMPF 19921 可用，需注入微信、有微信号风险，按需启用）。

---

## 附：MVP 最小闭环
**M0 复制骨架 → M0.5 G0 视觉闸门（捕获 + VLM 抽取 + SendInput 命中）→ M1 desktop+driver 骨架 → M2 单岗位投递 → M3 巡检 → M4 子集（预览+看板+收件箱）**：
置顶 BOSS小程序 → 截图抽一屏岗位 → gpt-5.5 打分（pipeline 决策）→ SendInput 发招呼 → 巡检发现回复 → 收件箱一键接管。
