---
标题: Hermes SeaTalk Plugin Agent 主动外发能力工作分解结构
状态: draft
更新日期: 2026-07-31
基线:
  hermes-agent 版本: v2026.7.30 (v0.19.1)
  参照实现: hermes-telex `telex` 工具的 `send_message` 动作
参考材料:
  - 上游移除 agent 可调 send_message 的决定 (hermes-agent commit c6c8abbad, PR #47856, 2026-06-17)
  - 上游认可的替代模式:平台原生发送工具 (`yb_send_dm` / `yb_send_sticker`,见 v2026.7.30 toolsets.py:324-326)
  - 参照实现 (../../hermes-telex/hermes_telex/tools.py:33-43, 238-256)
  - E2E 用例 E6 主动外呼 (../../openclaw-seatalk-test/src/cases.ts)
文档摘要: 为 SeaTalk 插件补齐 agent 主动外发能力,拆解为可执行任务、依赖关系、完成条件和验证方式。
---

# Hermes SeaTalk Plugin Agent 主动外发能力工作分解结构

## 1. 背景与范围

hermes-agent 自 commit `c6c8abbad`(2026-06-17,含于 v2026.6.19 及之后)移除了 **agent 可调用的核心
`send_message` 工具**,理由是"the agent should not decide on its own to fire off cross-platform
messages"。同一 commit 明确保留了发送引擎供非 agent 调用方(cron 投递、kanban notifier、
`hermes send` CLI)使用,并把 Yuanbao 的私聊引导改为指向**平台原生工具** `yb_send_dm`。

因此上游反对的是"通用跨平台工具让模型随意发消息",而非"agent 主动发消息"本身;**平台集成自
备原生发送工具是上游示范的模式**。hermes-telex 已按此模式实现(`telex` 工具的 `send_message`
动作),SeaTalk 尚缺,导致:

- E2E 用例 **E6(按邮箱主动外发)在 hermes ≥ v2026.6.19 上必然失败**——agent 无任何可用的
  发送工具。
- 插件工具描述仍指向已被移除的核心 `send_message`,**主动误导模型**(实测中 agent 依此尝试
  调用并报告"工具不存在")。

本 WBS 的范围:给 SeaTalk 插件补齐与 telex 对等的主动外发能力,目标白名单受控。

不在范围内:核心 `send_message` 的 `_parse_target_ref` 缺口(那是另一条路径,本方案绕开它);
群顶层媒体投递失败(A9/A10,根因在模型行为与 hermes 核心静默丢弃,插件无需改动)。

任务 ID 使用 `WS-xx`(Send),避免与 `W-xx` / `W2-xx` / `WC-xx` 混淆。

## 2. 设计决策

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 能力归属 | 扩展插件自有工具,不恢复核心 `send_message` | 上游模式(`yb_send_dm`);目标解析由插件负责,模型无需构造 target 字符串 |
| 目标范围 | **允许任意 target**,由白名单约束 | 用户决策;E6 需要按邮箱主动 DM 非当前会话对象 |
| 白名单来源 | 复用账号既有 `allow_from` / `group_allow_from` | 不新增配置面;与入站策略同一套语义 |
| 工具名 | `seatalk_query` → **`seatalk`** | 具备发送能力后 `_query` 名称会误导模型,而模型误判正是 E6 失败的形态;与 telex 命名对齐。已确认仅 tools.py 与测试引用,VM agent 记忆无引用 |
| 动作级开关 | 新增账号级 `tools` 映射 | 与 telex 对等,运维可单独关掉发送 |
| 媒体发送 | 支持本地路径附件 | 与 telex `media_paths` 对等 |

## 3. 任务清单

| ID | 任务 | 依赖 | 执行方式 | 覆盖范围 | 验收要点 |
| --- | --- | --- | --- | --- | --- |
| WS-00 | 账号级动作开关 `tools` | 无 | AFK | `SeaTalkAccountConfig.tools`、配置解析、默认值 | 未配置时全部动作默认开启;可按账号关闭单个动作 |
| WS-01 | 目标白名单校验 | WS-00 | AFK | 私聊查 `allow_from`、群查 `group_allow_from`、`*` 通配 | 不在白名单的目标返回错误 JSON 而非发出;邮箱按解析前后两种形态都能匹配 |
| WS-02 | `send_message` 动作 | WS-00, WS-01 | AFK | schema、handler、文本 + 媒体、目标解析复用 | 文本/媒体/图文混合可发;`account:` 前缀、`group/`、邮箱三种 target 均可用 |
| WS-03 | 工具改名与描述修正 | WS-02 | AFK | `seatalk_query` → `seatalk`、删除对核心 `send_message` 的指引 | 描述不再提及已移除的核心工具;注册名与测试同步更新 |
| WS-04 | 测试与文档 | WS-00 到 WS-03 | AFK | 单测、README | 白名单拒绝/放行、动作开关、邮箱解析、媒体路径均有覆盖;README 说明新动作与白名单语义 |
| WS-05 | 部署与 E6 验证 | WS-04 | HITL | VM 部署、重跑 E6 | E6 由 FAIL 转 PASS;需确认外发目标邮箱在 `allow_from` 内 |

## 4. 依赖关系

```text
WS-00 ─┬─> WS-01 ─> WS-02 ─> WS-03 ─> WS-04 ─> WS-05
       └───────────────^
```

## 5. 建议实施顺序

### Batch 1:能力实现

包含:WS-00、WS-01、WS-02、WS-03

交付目标:agent 可通过插件原生工具发送到白名单内的任意 SeaTalk 目标,工具语义自洽。

### Batch 2:测试与验证

包含:WS-04、WS-05

交付目标:离线单测覆盖关键分支;真实环境 E6 通过。

## 6. 任务明细

### WS-00 账号级动作开关 `tools`

目标:运维可按账号禁用单个工具动作(与 telex 对等)。

交付物:

- `SeaTalkAccountConfig.tools: dict[str, bool]`。
- 配置解析:`accounts.<id>.tools.<action>`,顶层 `extra.tools` 作为基础默认。
- 默认值:所有动作开启。

完成条件:

- 未配置 `tools` 时,全部动作可用。
- `tools: {send_message: false}` 使该动作返回错误 JSON,其余动作不受影响。
- 顶层与账号级遵循既有 merge 规则(账号覆盖顶层)。

验证方式:配置解析单测;handler 分支单测。

### WS-01 目标白名单校验

目标:主动外发只能送达账号白名单内的目标。

交付物:

- 校验函数:解析后的目标按类型查表——私聊查 `allow_from`,群查 `group_allow_from`。
- `*` 通配支持(与入站 `is_sender_allowed` 语义一致)。
- 拒绝时返回带 `error` 的 JSON,不触达 SeaTalk API。

完成条件:

- 邮箱形态目标:**解析前的邮箱**与**解析后的 employee_code** 任一命中白名单即放行
  (`allow_from` 既可配邮箱也可配 employee_code)。
- 群目标:raw `group_id` 命中 `group_allow_from` 才放行;`group_policy=disabled` 一律拒绝。
- 白名单为空时拒绝(fail closed),错误信息指明缺少白名单配置。
- 拒绝路径不产生任何 SeaTalk API 调用。

验证方式:白名单 matrix 单测(放行/拒绝/通配/空白名单/群与私聊)。

### WS-02 `send_message` 动作

目标:agent 可发送文本与媒体到指定 SeaTalk 目标。

交付物:

- schema 新增动作与参数:`target`、`text`、`media_paths`。
- handler 分支:解析 target → 白名单校验 → 发送。
- 目标解析复用 `parse_seatalk_target` + adapter 的 `_resolve_target`(自动支持 `account:` 前缀、
  `group/`、邮箱→employee_code)。
- 发送复用 adapter 的 `send` / `send_image_file` / `send_document`。

完成条件:

- 仅 `text`、仅 `media_paths`、两者皆有,三种组合均可发送。
- 二者皆空时返回错误 JSON。
- 图片扩展名走图片发送、其余走文档发送(与既有出站路径一致)。
- 目标解析失败(邮箱查不到人、格式非法)返回错误 JSON 且信息可定位。
- 无活跃 adapter 时返回明确错误(不静默失败)。

验证方式:handler 单测(注入 fake client/adapter),覆盖上述分支。

### WS-03 工具改名与描述修正

目标:工具名与描述如实反映能力,不再误导模型。

交付物:

- 注册名 `seatalk_query` → `seatalk`。
- 描述:移除 "use send_message(target=...) for outbound delivery" 一句,改为说明本工具自身
  的发送动作;保留读取动作说明。
- 同步更新引用该名称的测试。

完成条件:

- 描述中不出现对核心 `send_message` 工具的指引。
- 全仓库无残留 `seatalk_query` 引用。

验证方式:schema 断言单测;仓库检索。

### WS-04 测试与文档

目标:关键分支有离线覆盖,运维语义有文档。

交付物:

- 单测:白名单 matrix、动作开关、发送三种组合、邮箱解析、错误路径。
- README:新增动作说明、白名单语义、动作级开关配置示例。

完成条件:

- 全量 pytest 在标准环境与 hermes v2026.7.30 下均通过。
- README 说明"主动外发受 `allow_from` / `group_allow_from` 约束"。

验证方式:全量 pytest(两种环境);README 检查。

### WS-05 部署与 E6 验证

目标:真实环境验证主动外发可用。

交付物:

- VM 部署新插件并重启 gateway。
- E6 用例通过记录。

完成条件:

- E6 由 FAIL 转 PASS。
- 其余用例无回退(与本轮 31 pass 基线对比)。
- 前置确认:E2E 的外发目标邮箱(`SEATALK_TEST_OUTBOUND_EMAIL`)在账号 `allow_from` 内,
  否则按 WS-01 会被正确拒绝——此时应调整测试目标或白名单,而非放宽校验。

验证方式:重跑 seatalk 套件;必要时单跑 E6。

## 7. 覆盖关系

| 目标 / 决策 | 覆盖任务 |
| --- | --- |
| 上游模式:平台原生发送工具 | WS-02 |
| 允许任意 target + 白名单约束 | WS-01, WS-02 |
| 邮箱→employee_code 解析 | WS-01, WS-02 |
| 与 telex 能力对等(含动作级开关) | WS-00, WS-02, WS-03 |
| 工具语义自洽、不误导模型 | WS-03 |
| E6 转 PASS | WS-05 |
