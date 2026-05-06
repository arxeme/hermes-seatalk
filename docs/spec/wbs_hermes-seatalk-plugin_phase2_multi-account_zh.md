---
标题: Hermes SeaTalk Plugin Phase 2 多帐号工作分解结构
状态: draft
更新日期: 2026-05-05
参考材料:
  - Hermes SeaTalk Plugin Phase 2 多帐号技术设计 (./td_hermes-seatalk-plugin_phase2_multi-account_zh.md)
  - Hermes SeaTalk Phase 2 多帐号运行时架构决策 (./tdr_hermes-seatalk-plugin_phase2_multi-account-runtime_zh.md)
  - Hermes SeaTalk Plugin Phase 2 多帐号测试计划 (../test/tp_hermes-seatalk-plugin_phase2_multi-account_zh.md)
文档摘要: 将 Phase 2 多帐号技术设计拆解为可执行任务、依赖关系、完成条件和验证方式。
---

# Hermes SeaTalk Plugin Phase 2 多帐号工作分解结构

## 1. 范围

本 WBS 基于 `td_hermes-seatalk-plugin_phase2_multi-account_zh.md`，目标是在现有
hermes-seatalk plugin 基础上实现 SeaTalk 多帐号能力。Phase 2 只定义 accounts-only
最终形态，不提供单帐号配置迁移流程。

实现边界：

- Hermes 仍只注册一个 platform：`seatalk`。
- 多帐号能力封装在 plugin 内部的 `SeaTalkAccountRuntime`。
- 所有 SeaTalk runtime 配置位于 `platforms.seatalk.extra.accounts`。
- `app_secret` / `signing_secret` 直接保存在 `config.yaml`。
- `dm_policy` 只支持 `allowlist` / `open`，不支持 `pairing`。
- 配置校验采用 all-or-nothing；runtime 启动采用 per-account independent。
- 入站 session 的 account 维度由 `source.chat_id` 承载，`source.user_id` 不加 account prefix。
- Webhook shared endpoint 先用 candidate signing secrets 验签，再解析 JSON。

任务 ID 使用 `W2-xx`，避免与 Phase 1 WBS 的 `W-xx` 混淆。

## 2. 任务清单

| ID | 任务 | 依赖 | 执行方式 | 覆盖范围 | 验收要点 |
| --- | --- | --- | --- | --- | --- |
| W2-00 | Accounts 配置模型与校验 | 无 | AFK | config parser、account merge、policy validation、`REQUIRED_ENV` | accounts-only 配置可解析；非法配置整体失败；`.env` secrets 不参与校验 |
| W2-01 | Hermes 注册与内部授权闸门 | W2-00 | AFK | `register(ctx)`、`check_fn`、`validate_config`、internal `allow_all_env` | `check_fn` 只查依赖；`allow_all_env=HERMES_SEATALK_ALLOW_ALL`；不暴露用户 allow-all |
| W2-02 | 多 AccountRuntime 与状态聚合 | W2-00, W2-01 | AFK | runtime map、client/dispatcher/coalescer、secret redaction、per-account state | 每个 account 独立 runtime；secret 跨 account 脱敏；runtime failure 按 account 隔离 |
| W2-03 | 入站 account context 与授权策略 | W2-02 | AFK | dispatcher account context、SessionSource、per-account DM/group policy | `chat_id` 带 account prefix；`user_id` 不带 prefix；DM/group policy 按 account 生效 |
| W2-04 | Relay 多帐号 runtime | W2-02, W2-03 | AFK | 多 relay client、per-account reconnect/auth failure、payload app_id 校验 | 多个 relay account 独立连接；单 account auth/network failure 不影响其他 account |
| W2-05 | Spike: Webhook challenge 与签名行为验证 | W2-00 | HITL | SeaTalk webhook challenge payload、签名 header、app_id presence | 确认 challenge 形态；验证 shared endpoint 先验签后解析策略可用 |
| W2-06 | Webhook 多帐号 runtime | W2-02, W2-03, W2-05 | AFK | shared server、candidate secret verification、account dispatch resolver | 同 endpoint 多 account 可验签路由；challenge 不依赖 app_id；普通事件缺 app_id 被拒绝 |
| W2-07 | 出站 account 选择与 Hermes patch | W2-02 | AFK | target parser、metadata priority、home channel env、cron、send_message patch | account prefix 先解析；home/cron 读取 Hermes env target；内置平台行为不变 |
| W2-08 | Setup wizard、文档与发布边界 | W2-00 到 W2-07 | AFK | account 管理 wizard、README/env.example、publish branch | wizard 写 accounts 配置；README 说明 config.yaml secrets；publish 分支只包含 runtime 文件 |
| W2-09 | 自动化测试与回归收敛 | W2-00 到 W2-08 | AFK | pytest 覆盖、离线 mock、Phase 1 回归、测试报告入口 | Phase 2 核心路径可离线验证；Phase 1 关键能力不回退 |

## 3. 依赖关系

```text
W2-00
  -> W2-01
      -> W2-02
          -> W2-03
              -> W2-04
              -> W2-06
          -> W2-07
W2-05 -> W2-06
W2-08 depends on W2-00..W2-07
W2-09 depends on W2-00..W2-08
```

## 4. 建议实施顺序

### Batch 1：配置与注册基础

包含：W2-00、W2-01

交付目标：

- accounts-only 配置模型落地。
- Hermes platform 注册和 internal allow-all 授权闸门落地。
- adapter 创建前的静态校验边界清晰。

### Batch 2：多 runtime 核心与入站身份

包含：W2-02、W2-03

交付目标：

- 单 adapter 内部管理多个 account runtime。
- 入站事件带 account context。
- session key 不跨 account 串联。
- per-account policy 生效。

### Batch 3：Relay 多帐号

包含：W2-04

交付目标：

- 当前 relay 部署路径支持多帐号。
- relay auth/network failure 按 account 隔离。
- 可先满足测试 VM 的主要运行模式。

### Batch 4：Webhook 风险验证与实现

包含：W2-05、W2-06

交付目标：

- 实测或官方文档确认 webhook challenge payload。
- shared webhook endpoint 支持多帐号签名验证和路由。
- W2-05 可在 Batch 1 完成后作为独立 HITL track 提前并行执行；本 batch 中的
  W2-06 必须等待 W2-05 结论确认后再实现。

### Batch 5：出站、设置与发布

包含：W2-07、W2-08

交付目标：

- `send_message`、home channel、cron 均支持 account-qualified target selection。
- setup wizard 和 README 暴露最终 accounts-only 配置。
- publish branch 发布边界明确。

### Batch 6：测试与回归收敛

包含：W2-09

交付目标：

- 自动化测试覆盖 Phase 2 关键行为。
- Phase 1 单帐号行为以 default account 形态继续可用。
- 形成可用于后续 batch TR 的测试命令和报告入口。

## 5. 任务明细

### W2-00 Accounts 配置模型与校验

目标：将单帐号配置升级为 `platforms.seatalk.extra.accounts` accounts-only 模型。

交付物：

- `SeaTalkAccountConfig` / `SeaTalkPolicy` 等 account 配置模型。
- `_accounts_from_extra(extra)`。
- `_merge_account_config(base, account)`。
- `_validate_seatalk_config(config)` 的 accounts 校验。
- `REQUIRED_ENV = []`。

完成条件：

- `accounts` 缺失、空、非法类型时配置校验失败。
- 顶层默认字段可 shallow merge 到 account，account 字段覆盖顶层。
- 任一 enabled account 缺少 `app_id`、`app_secret`、`signing_secret`、mode 必需项时整体失败。
- relay account 缺少 `relay_url` 时整体失败。
- webhook account 的 `webhook_port` / `webhook_path` 非法时整体失败。
- account id 必须匹配 `^[a-z0-9][a-z0-9_.-]*$`。
- `dm_policy=pairing` 被拒绝。
- `group_allow_from` 中出现 `group/<id>` 被拒绝。
- 重复 `app_id` 被拒绝。
- `.env` secrets 不参与校验。

验证方式：

- 配置 parser 单测。
- account merge table-driven tests。
- invalid config matrix 单测。

### W2-01 Hermes 注册与内部授权闸门

目标：让 Hermes core 的 platform 授权闸门放行已通过 SeaTalk dispatcher 授权的事件。

交付物：

- `check_seatalk_requirements()` 改为只检查 Python 依赖。
- `register(ctx)` 注册 `validate_config=_validate_seatalk_config`。
- `register(ctx)` 设置内部 `HERMES_SEATALK_ALLOW_ALL=true`。
- `ctx.register_platform(..., allow_all_env="HERMES_SEATALK_ALLOW_ALL")`。

完成条件：

- `check_fn` 不读取 `.env` / `config.yaml`，只验证依赖可导入。
- `required_env` 为空，Hermes setup/status 不再提示 `SEATALK_APP_SECRET` / `SEATALK_SIGNING_SECRET`。
- platform 注册不传 `allowed_users_env`。
- 内部 `HERMES_SEATALK_ALLOW_ALL` 不写入用户 `.env`。
- 多次 `register(ctx)` 幂等，不重复 patch 或重复注册。

验证方式：

- register fake context 单测。
- env isolation 单测。
- Hermes registry auth metadata 单测。

### W2-02 多 AccountRuntime 与状态聚合

目标：在一个 `SeaTalkAdapter` 内管理多个独立 account runtime。

交付物：

- `SeaTalkAccountRuntime`。
- `SeaTalkAdapter.accounts` / `SeaTalkAdapter._runtimes`。
- 每 account 独立 client、dispatcher、relay client、coalescer。
- account runtime 状态：`running`、`auth_failed`、`retrying`、`stopped`、`last_error`。
- adapter 聚合状态。
- `_build_all_secrets() -> list[str]`，在所有 account runtime 构造前完成全量 secret
  收集。
- 全 account secret redaction set。

完成条件：

- 每个 enabled account 创建一个 runtime。
- disabled account 不创建 runtime。
- 每个 runtime 使用自己的 client/dispatcher/coalescer。
- 所有 enabled account 的 `app_secret` / `signing_secret` 都注入每个 client 的 `log_secrets`。
- 一个 account runtime 永久失败不停止其他 account。
- 至少一个 account running/retrying 时 platform 不 fatal。
- 所有 enabled accounts 均永久失败时 platform fatal。
- connect/disconnect/error 日志包含 `account_id`。

验证方式：

- adapter runtime map 单测。
- secret redaction 单测。
- per-account state aggregation 单测。
- log capture 单测。

### W2-03 入站 account context 与授权策略

目标：入站事件携带 account context，并按 account 执行授权策略。

交付物：

- dispatcher 注入 `account_id`。
- `raw_message["seatalk_account_id"]`。
- account-qualified `source.chat_id`。
- per-account `dm_policy` / `allow_from`。
- per-account `group_policy` / `group_allow_from` / `group_sender_allow_from`。

完成条件：

- 入站 DM `source.chat_id` 为 `<account_id>:<dm_target>`。
- 入站 group `source.chat_id` 为 `<account_id>:group/<seatalk_group_id>`。
- `source.user_id` 不加 account prefix。
- `source.thread_id` 不拼进 `source.chat_id`。
- 同一 sender 在不同 account 下生成不同 session key。
- `allow_from` 按 email/employee code 匹配。
- `group_allow_from` 只匹配 raw SeaTalk `group_id`。
- `group_sender_allow_from` 在 `group_policy=open/allowlist` 下仍生效。

验证方式：

- dispatcher normalization 单测。
- session key 单测。
- authorization matrix 单测。

### W2-04 Relay 多帐号 runtime

目标：支持多个 relay account 独立连接、重连和 dispatch。

交付物：

- 每个 relay account 一个 `SeaTalkRelayClient`。
- relay dispatch 绑定对应 account runtime。
- payload `app_id` 校验。
- per-account relay state aggregation。

完成条件：

- 两个 relay accounts 可同时启动。
- relay event 进入正确 account dispatcher。
- relay payload `app_id` 存在且不匹配 runtime `app_id` 时被丢弃并记录 warning。
- 单个 account `auth_fail` 或 `replaced` 标为永久失败，不影响其他 account。
- 单个 account 网络错误 / heartbeat timeout 进入 retrying，不影响其他 account。
- 所有 relay auth/network failure 按 account 隔离；platform-level fatal 由 W2-02
  跨 relay/webhook runtime 聚合决定。

验证方式：

- mock WebSocket server 集成测试。
- multi relay routing 单测/集成测试。
- auth failure isolation 测试。
- reconnect isolation 测试。

### W2-05 Spike: Webhook challenge 与签名行为验证

目标：在实现 shared webhook 前确认 SeaTalk challenge payload 和签名行为。

交付物：

- SeaTalk webhook challenge payload 记录。
- Signature header 生成/校验样例。
- shared endpoint 多 account 验签策略结论。
- 若发现协议限制，回填 TD §5.2 / §11。

完成条件：

- 明确 challenge payload 是否携带 `app_id`。
- 明确 challenge 是否使用同一 Signature 规则。
- 明确普通事件是否总携带 `app_id`。
- 若普通事件可能缺少 `app_id`，TD 和 TP 中保留拒绝行为。
- 实测记录可复现，包含 sanitized request/response。

验证方式：

- HITL SeaTalk Bot App 实测。
- 或官方文档引用加本地签名模拟测试。

### W2-06 Webhook 多帐号 runtime

目标：支持 shared webhook server 对多个 account 验签和路由。

交付物：

- webhook server candidate secret resolver。
- account dispatch resolver。
- shared `(host, port, path)` server manager。
- challenge 处理不依赖 payload `app_id`。

完成条件：

- 同 endpoint 下多个 webhook accounts 共享一个 server。
- 签名验证发生在 JSON 解析之前。
- 无 candidate secret 验签通过时返回 403。
- payload `app_id` 与验签 account 不一致时返回 403。
- challenge payload 无 `app_id` 时仍返回 challenge。
- 普通事件缺少 `app_id` 时被拒绝。
- unknown `app_id` 不泄露可枚举信息。

验证方式：

- aiohttp webhook handler 集成测试。
- multi-account signature positive/negative tests。
- challenge without app_id 测试。
- malformed payload 测试。

### W2-07 出站 account 选择与 Hermes patch

目标：出站目标、home channel env、cron 均能选择正确 account。

交付物：

- `SeaTalkTarget.account_id`。
- `parse_seatalk_target(target_ref, known_accounts=None)`。
- `SeaTalkAdapter._resolve_target()` account selection。
- `SeaTalkAdapter.get_chat_info()` account selection。
- `send()` / `send_typing()` / media send 使用目标 account runtime。
- `_patch_send_message_tool()` 支持 account-qualified target。
- `_patch_home_channel()` / `_patch_cron_scheduler()` 读取 `SEATALK_HOME_CHANNEL*`
  env，并支持 account-qualified target。

完成条件：

- account prefix 在 group/email/thread 解析前剥离。
- `seatalk:` platform prefix 在 account prefix 解析前剥离，
  `seatalk:staging:EmpABC` 可正确解析。
- `SeaTalkTarget.account_id: str | None = None`，默认 None 保持 Phase 1 构造调用兼容；
  Phase 2 account-resolved 路径赋值具体 account id。
- `staging:EmpABC` 解析为 account `staging`、target `EmpABC`，不是 thread。
- `staging:group/<seatalk_group_id>:ThreadXYZ` 正确保留 thread。
- `metadata["seatalk_account_id"]` 优先级高于 target prefix。
- 无 account prefix 时按 `default` / 第一个 enabled account 选择。
- `get_chat_info("staging:EmpABC")` 使用 staging runtime client，不把 `EmpABC`
  误解析为 thread id。
- `SEATALK_HOME_CHANNEL=staging:...` 生效。
- cron delivery 使用 `SEATALK_HOME_CHANNEL` account-qualified target。
- 内置平台 target parser 行为不变。

验证方式：

- target parser table-driven tests。
- send path mock runtime tests。
- home/cron patch tests。
- built-in platform regression tests。

### W2-08 Setup wizard、文档与发布边界

目标：用户可通过 setup wizard 和 README 配置 accounts-only SeaTalk plugin，并将
home channel 写入 Hermes 标准 env 项。

交付物：

- account 管理式 setup wizard。
- README accounts 配置说明。
- `env.example` 移除 SeaTalk secret env 依赖。
- publish branch 发布说明。

完成条件：

- wizard 支持 add/edit/disable/remove account。
- wizard 不写 home channel 到 `config.yaml`，而是写 `SEATALK_HOME_CHANNEL*` 到 `.env`。
- wizard 不写 SeaTalk secrets 到 `.env`，secrets 只写 `config.yaml` accounts。
- wizard 不展示 `pairing`。
- README 明确 `config.yaml` 包含 secrets。
- README 区分 `group_allow_from` raw group id 与 `SEATALK_HOME_CHANNEL` target 格式。
- README 说明 `publish` 分支只包含 runtime 文件和 README。
- deploy 脚本不默认覆盖远端 `config.yaml`。

验证方式：

- wizard source inspection / prompt flow 单测。
- README assertion tests。
- publish script dry-run / branch content check。

### W2-09 自动化测试与回归收敛

目标：建立 Phase 2 测试覆盖，并保护 Phase 1 已有行为。

交付物：

- Phase 2 单测和集成测试。
- Phase 1 回归测试筛选。
- batch 测试命令。
- 测试报告模板入口。

完成条件：

- `uv run pytest` 可离线运行核心测试。
- 不需要真实 SeaTalk secrets 即可覆盖 config、runtime、relay/webhook mock、outbound parser。
- env、registry、monkey patch 状态在测试间隔离。
- Phase 1 单帐号路径在 `default` account 下可继续工作。
- E2E runbook 增补多 account 手工验证步骤。

验证方式：

- 完整 pytest。
- targeted pytest per batch。
- E2E checklist 人工验证。

## 6. 覆盖关系

| TD 目标 / 决策 | 覆盖任务 |
| --- | --- |
| `platforms.seatalk.extra.accounts` accounts-only | W2-00, W2-08 |
| credentials 存入 `config.yaml` | W2-00, W2-08 |
| 单 Hermes platform + 多 AccountRuntime | W2-01, W2-02 |
| Relay 多帐号 | W2-04 |
| Webhook 多帐号 | W2-05, W2-06 |
| account-qualified `source.chat_id` | W2-03 |
| `source.user_id` 不加 account prefix | W2-03 |
| per-account DM/group policy | W2-03 |
| internal `allow_all_env` | W2-01 |
| secret redaction 跨 account | W2-02 |
| target account prefix | W2-07 |
| home channel env / cron account selection | W2-07 |
| setup wizard accounts 管理 | W2-08 |
| publish branch runtime 边界 | W2-08 |
| 自动化与联调验证 | W2-09 |
| forwarded 消息嵌套数组 / 媒体 / 发送者前缀 | W2-10 |
| quoted 消息去重（同窗口多次引用同一 message_id）| W2-10 |
| 媒体下载一次重试 | W2-10 |
| seatalk 工具多帐号 account_id 参数 | W2-11 |

---

追加任务（OpenClaw 对齐与工具增强）

| ID | 任务 | 依赖 | 执行方式 | 覆盖范围 | 验收要点 |
| --- | --- | --- | --- | --- | --- |
| W2-10 | OpenClaw 消息解析对齐 | W2-09 | AFK | forwarded 嵌套数组 + 媒体 + 发送者前缀；quoted 引用去重；媒体下载一次重试 | forwarded 媒体不丢失；嵌套数组递归处理；同 debounce 窗口同一 quoted_id 只出现一次；媒体下载失败后自动重试一次 |
| W2-11 | SeaTalk 工具多帐号支持 | W2-10 | AFK | seatalk tool schema 增加可选 `account_id`；`_get_seatalk_tool_client` 支持按 account_id 选择 runtime | 指定 account_id 时使用对应 account 的 client；account_id 不存在时返回错误 JSON；不指定时保持默认 account 行为 |

### W2-10 OpenClaw 消息解析对齐

目标：使 hermes-seatalk 的入站消息解析与 openclaw-seatalk 在转发消息、引用去重和媒体重试行为上对齐。

交付物：

- `_resolve_forwarded_items(items)` 新方法：递归处理 `content` 列表中的嵌套数组，包含媒体下载和发送者前缀。
- 更新 `_resolve_message_content` 中的 `combined_forwarded_chat_history` 分支，使用新方法并返回媒体。
- `_emit_parts` 改为追踪 `seen_quoted_ids`，同 debounce 窗口内相同 `quoted_message_id` 的 reply_to_text 只输出一次。
- `_normalize_dm` / `_normalize_group` 不再直接将 `reply_to_text` 拼入 `text`，由 `_emit_parts` 负责最终拼接。
- `_download_media` 在第一次失败后自动重试一次。

完成条件：

- 转发消息中含 image/file/video 时，media_urls / media_types 正确返回（不丢失）。
- 转发消息 `content` 为列表的每个 dict 项，若有 `sender` 字段则前缀 `{sender_name}: `。
- `content` 含嵌套列表（list of list）时递归展开，不崩溃也不丢弃内容。
- 同一 debounce 窗口内两条消息引用相同 `quoted_message_id` 时，最终 `event.text` 中 quoted 文本只出现一次。
- 媒体下载第一次抛出非 ValueError 异常时自动重试一次；第二次失败则进入 media_errors。
- 现有测试 `test_t06_05_quoted_message`、`test_t06_06_attachment_failure_degrades` 保持通过。

验证方式：

- `tests/test_w06_dispatcher.py` 追加 forwarded 媒体、发送者前缀、嵌套数组、quoted 去重、媒体重试测试。

### W2-11 SeaTalk 工具多帐号支持

目标：`seatalk` tool 支持通过可选 `account_id` 参数指定调用哪个 SeaTalk account 的 client。

交付物：

- `SEATALK_TOOL_SCHEMA` 中追加可选 `account_id` string 参数。
- `_get_seatalk_tool_client(account_id=None)` 支持按 account_id 查找对应 runtime client。
- `make_seatalk_tool_handler` 的 handler 将 `args.get("account_id")` 传给 client getter。
- 可注入 get_client 签名更新为接受 `account_id=None` 关键字参数，保持单元测试可用。

完成条件：

- 指定已存在 account_id 时使用对应 account runtime client。
- 指定不存在 account_id 时 client getter 返回 None，handler 返回含 `"error"` 的 JSON。
- 不指定 account_id 时回退到 default account，行为与 W2-09 之前一致。
- `tests/test_w11_seatalk_tools.py` 追加 account_id 相关测试。

验证方式：

- `tests/test_w11_seatalk_tools.py` 追加 schema 字段验证、account_id 传递验证、account 不存在错误测试。
