# boss-wxapp-autoapply

PC **微信小程序版 BOSS直聘** 的半自动求职系统：**非侵入视觉控制**（截图 + gpt-5.5 多模态定位 + SendInput 模拟点击）驱动小程序，自动筛选 → 半自动投递 + 打招呼 → HR 回复巡检转人工。

派生自真机安卓版 [`ms`](../ms)（boss-autoapply）：**决策/数据/流水线核心原样复用**，仅把"adb 控安卓真机"换成"桌面控小程序窗口"。设计与验证见 `.omc/plans/boss-wxapp-autoapply-plan.md`。

## 为什么非侵入视觉

- **零注入**：只读窗口像素（`PrintWindow`/屏幕 BitBlt）+ 发系统输入（`SendInput`），不碰微信进程 → 微信号风险≈0。
- 对照 CDP/DOM 方案（需注入微信、有封号风险）降为 Follow-up 可选后端。

## 架构

```
React 精简控制台（投递看板/HR收件箱/规则/日志/岗位流/窗口预览）
   │ REST · SSE                           ← 端点 localhost+token+Origin 鉴权
┌──▼──────────────────────────────────────────────────────┐
│ FastAPI                                                   │
│  pipeline（唯一投递权威）: collector → screener(LLM打分)   │
│                            → dispatcher(幂等状态机+限速)   │
│  inbox_watcher 常驻巡检 → HR 回复转人工                    │
│  ─────────────────────────────────────────────           │
│  pages/boss_wxapp.py  BossWxappDriver（同 ms 契约）        │
│  desktop/  window(找窗口) · capture(截图) · input(点击)    │
│  llm/  gpt-5.5 httpx 直连（文本 high / 视觉 low）          │
└──────────────────────────────────────────────────────────┘
              非侵入控制 PC 微信「BOSS直聘」小程序窗口
```

## 关键实测结论（G0，见 plan §2.5）

- **LLM 用 httpx 直连**：openai SDK 被 gpt.pkpp.cn 的 Cloudflare WAF 拦（403），httpx 裸 POST 正常。
- **推理分级**：视觉定位/抽取 `reasoning_effort=low`（~快），文本打分用 `high`。
- **截图**：先 `SetForegroundWindow` 触发重绘，再屏幕 DC BitBlt（后台 GPU 窗口直接 PrintWindow 会空白）。
- **点击**：归一化坐标按 DPI 1.5 映射到物理像素；点标题/薪资/按钮区，勿点技能标签或 HR 行。

## 开发

### 后端（uv）

```bash
cd backend
uv sync --extra dev
cp .env.example .env        # 填入 GPT_API_KEY
# 前置：在 PC 微信里打开「BOSS直聘」小程序并停在职位列表
uv run uvicorn app.main:asgi_app --host 127.0.0.1 --port 8000
uv run pytest
```

### 前端（pnpm）

```bash
cd frontend
pnpm install
pnpm dev
```

## 状态

- **M0/M1 ✅**：仓库骨架 + `desktop/` 桌面层（G0 验证通过）+ httpx LLM + `BossWxappDriver`（窗口/截图/列表抽取/点击）。
- **M2**：详情字段抽取 + 投递动作（点「立即沟通」）。
- **M3**：HR 巡检。**M4**：精简前端控制台。**M5**：健壮性 + VLM 预算熔断。

> 半自动边界：自动筛选 + 投递 + 打招呼；HR 回复转人工接管，系统不自动续聊。
