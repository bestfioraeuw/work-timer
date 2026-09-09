# Loop context 001 — 2026-09-09 01:32

后续 tick **先读本目录最新 `context-*.md` 和 `state.json`**，不要重扫整仓、不要重读 DESIGN.md 全文。

## 任务

自我迭代「工作钟」。你是产品经理 + 设计师。唯一用户：28 岁大陆男软件工程师。目标：记录上下班、工作/休息、每天工作内容，要顺手。

技能：`/loop`（本地动态心跳）`/ponytail`（full）`/front-design`（视觉跟 `DESIGN.md`，不另起炉灶）。

## 硬约束（用户 01:36 补）

- **真机是 macOS。** `start.command` 必须一直能用。不要做只在 Windows 成立的能力（路径、快捷键、启动方式）。Windows 启动器可留，但不是设计基准。Mac 上用系统字体（SF Pro / `-apple-system`），不要为 Windows 拉 Google Fonts。
- **保持小巧。** 零新依赖，不新页面，不新配置，不菜单栏/托盘/打包成 App。乔布斯：删到只剩记录上下班和工作内容。一次只打磨一件顺手的事。

退出：同一问题调试失败 >5 次；或超过 `2026-09-09T04:29:00+08:00`。退出后 **commit 当前分支并 push 远程**。

Context ≥85%：写下一份 `context-00N.md`，再概括，然后继续。不要重做已落地的活。

## 产品（已存在，勿重做）

零依赖 Python：`app.py` + `static/index.html` + SQLite `data/clock.db`。端口 8765。测试：`python test_clock.py`。

已有：打卡/下班、工作/休息分段、校准/重置下班、日历、时段风景、日报自动保存、年导出 MD/Excel、下班后时间轴。UI 必须用 DESIGN.md 的 Apple tile 语言（唯一强调色 `#0066cc`，无第二品牌色/装饰渐变/卡片阴影）。

分支：`feature/loop`（与 `main`/`origin/main` 同 commit `28a20c1`，本轮改动未提交）。

## Tick 0 已改（验证前不要重做）

卡点：工作时不能换任务（须先休息）；欢迎页必须先「上班打卡」。

落地：

- `app.recent_tasks()`：最近 6 个不重复工作事项；挂在 `day_payload["recent_tasks"]`。
- 欢迎页：输入「正在做什么」+「开始今天」。空 = 只打卡；有字/点芯片 = 打卡并开工。
- 工作时输入框不藏，按钮变「换一件事」；芯片一点换活。
- `/` 聚焦事项框（不在 input/textarea 里时）。
- 「校准时间」折叠，入定时隐藏。
- `#in` 仍在 DOM 但 hidden。

`python test_clock.py` 已通过。无浏览器 MCP，用测试/curl 验。

## Tick 1（01:44）

忘下班：今天打开时若昨天未收工，hero 上一句「昨天还没下班」，点一下按 23:59 收下。过去日点下班同样落到当天 23:59。欢迎语不再说「先打卡」。

## 下一轮可打磨（每次只做一件）

1. 日报：分段出来后，空日报给一句可改的草稿。
2. 键盘：休息 / 下班快捷键（Mac 与 Windows 都能用，不要只绑 Ctrl）。
3. 芯片在第一次使用前是空的，无示例。

不要做：新依赖、新颜色、新页面、配置系统。

## 不要再读

DESIGN.md 全文、index.html 全文、历史 agent transcripts。UI 改动对照 DESIGN 组件名即可：`button-primary`、`search-input`、`configurator-option-chip`、`product-tile-*`、`store-utility-card`。
