---
标题: Hermes SeaTalk Plugin Phase 2 多帐号测试计划
状态: draft
更新日期: 2026-05-05
参考材料:
  - Hermes SeaTalk Plugin Phase 2 多帐号技术设计 (../spec/td_hermes-seatalk-plugin_phase2_multi-account_zh.md)
  - Hermes SeaTalk Plugin Phase 2 多帐号工作分解结构 (../spec/wbs_hermes-seatalk-plugin_phase2_multi-account_zh.md)
文档摘要: 定义 Phase 2 多帐号能力的自动化测试、集成测试和真实 SeaTalk 联调验证。
---

# Hermes SeaTalk Plugin Phase 2 多帐号测试计划

## 1. 测试目标

本测试计划覆盖 hermes-seatalk Phase 2 多帐号能力，包括 accounts-only 配置、
Hermes 注册授权边界、多 AccountRuntime、relay/webhook 多帐号路由、出站 account
选择、setup wizard 与发布边界。

测试原则：

- 自动化测试默认不依赖真实 SeaTalk credentials。
- 配置校验错误必须尽早失败。
- runtime 失败必须按 account 隔离。
- 每个测试用例都映射到 WBS `W2-xx`。
- Phase 1 的单帐号能力通过 `default` account 形态保留回归覆盖。
- SeaTalk webhook challenge payload 形态需要 HITL 实测或官方文档确认。

## 2. 测试环境

| 类型 | 工具/方式 | 用途 |
| --- | --- | --- |
| 单元测试 | `pytest` | config parser、target parser、auth policy、runtime state |
| 异步测试 | `pytest-asyncio` | relay client、webhook handler、adapter async send/connect |
| HTTP mock | `aiohttp` test server | webhook shared endpoint、OpenAPI mock |
| WebSocket mock | `aiohttp` WebSocket server | multi relay、auth_fail、reconnect、heartbeat timeout |
| 环境隔离 | pytest fixture | env var、registry、patch 状态隔离 |
| 日志验证 | `caplog` | secret redaction、account_id 日志字段 |
| HITL 联调 | SeaTalk Bot App | webhook challenge 与真实多 account 行为 |

默认命令：

```bash
uv run pytest
```

建议按范围执行：

```bash
uv run pytest tests/test_w01_registration.py
uv run pytest tests/test_w05_relay.py
uv run pytest tests/test_w07_authorization.py
uv run pytest tests/test_w08_runtime_patch.py
uv run pytest tests/test_w09_operations_docs.py
```

`test_wXX_*.py` 是 Phase 1 回归测试，继续验证 default account 形态下的既有行为；
`test_p2_*.py` 是 Phase 2 新增测试，覆盖多 account 行为。Batch 命令会按需要同时运行
两类测试，Batch 6 全量回归时必须合并执行。

Phase 2 实施后可新增更细分的测试文件，例如：

```text
tests/test_p2_config_accounts.py
tests/test_p2_runtime_accounts.py
tests/test_p2_dispatcher_accounts.py
tests/test_p2_relay_accounts.py
tests/test_p2_webhook_accounts.py
tests/test_p2_outbound_accounts.py
tests/test_p2_setup_docs.py
```

## 3. 自动化测试用例

### T2-00 Accounts 配置模型与校验

覆盖 WBS：W2-00

| 用例 | 类型 | 断言 |
| --- | --- | --- |
| T2-00-01 accounts 缺失失败 | unit | `platforms.seatalk.extra.accounts` 缺失、空 dict、非 dict 时 `_validate_seatalk_config` 返回 false |
| T2-00-02 enabled false 处理 | unit | 顶层 `enabled=false` 禁用 platform；account `enabled=false` 不创建 runtime 且不参与必填校验 |
| T2-00-03 顶层默认 merge | unit | 顶层 `dm_policy` / `group_policy` / `processing_indicator` 被 account 继承，account 字段覆盖顶层 |
| T2-00-04 credentials 完整性 | unit | enabled account 缺 `app_id` / `app_secret` / `signing_secret` 任一项时整体失败 |
| T2-00-05 relay 必填 | unit | `mode=relay` 缺 `relay_url` 时整体失败 |
| T2-00-06 webhook 必填 | unit | `mode=webhook` 的 port/path 非法时整体失败 |
| T2-00-07 account id 校验 | unit | 空、含大写、冒号、斜杠、空格、首字符非法的 account id 被拒绝 |
| T2-00-08 重复 app_id | unit | enabled accounts 中重复 `app_id` 被拒绝 |
| T2-00-09 policy enum | unit | `dm_policy` 仅允许 `allowlist/open`；`group_policy` 仅允许 `disabled/allowlist/open` |
| T2-00-10 pairing 拒绝 | unit | `dm_policy=pairing` 在 Phase 2 中被拒绝 |
| T2-00-11 group id 格式 | unit | `group_allow_from` 中任一值以 `group/` 开头时配置失败 |
| T2-00-12 env secrets 不参与 | unit | 未设置 `SEATALK_APP_SECRET` / `SEATALK_SIGNING_SECRET` 但 accounts 中有 secret 时校验成功 |

### T2-01 Hermes 注册与内部授权闸门

覆盖 WBS：W2-01

| 用例 | 类型 | 断言 |
| --- | --- | --- |
| T2-01-01 check_fn 只查依赖 | unit | `check_seatalk_requirements()` 不读取 `.env` / `config.yaml`；`aiohttp` 可导入时返回 true |
| T2-01-02 REQUIRED_ENV 为空 | unit | `REQUIRED_ENV == []`，setup/status 不提示 SeaTalk secret env |
| T2-01-03 register 使用 allow_all_env | unit | fake context 记录 `allow_all_env="HERMES_SEATALK_ALLOW_ALL"` |
| T2-01-04 不注册 allowed_users_env | unit | fake context 中没有 `allowed_users_env` 或该值为空 |
| T2-01-05 内部 env 设置 | unit | `register(ctx)` 设置 `os.environ["HERMES_SEATALK_ALLOW_ALL"] == "true"` |
| T2-01-06 不写用户 env 文件 | unit | setup wizard / register 不向 `.env` 写 `HERMES_SEATALK_ALLOW_ALL` |
| T2-01-07 validate_config 承担 accounts 校验 | unit | registry `validate_config` 指向 accounts 校验函数，非法 accounts 阻止 adapter 创建 |
| T2-01-08 register 幂等 | unit | 重复 `register(ctx)` 不重复注册平台、不重复 patch |

### T2-02 多 AccountRuntime 与状态聚合

覆盖 WBS：W2-02

| 用例 | 类型 | 断言 |
| --- | --- | --- |
| T2-02-01 runtime map 创建 | unit | 两个 enabled accounts 创建两个 runtime，disabled account 被跳过 |
| T2-02-02 runtime 隔离 | unit | 每个 runtime 拥有独立 client、dispatcher、coalescer |
| T2-02-03 secret 跨 account 脱敏 | unit | 任一 account 的 `app_secret` / `signing_secret` 都存在于每个 client 的 `log_secrets` |
| T2-02-04 状态字段 | unit | runtime state 记录 `running/auth_failed/retrying/stopped/last_error` |
| T2-02-05 单 account 永久失败隔离 | unit | 一个 runtime auth_failed 不停止其他 runtime |
| T2-02-06 聚合非 fatal | unit | 至少一个 runtime running/retrying 时 platform 不 fatal |
| T2-02-07 聚合 fatal | unit | 所有 enabled runtimes 均永久失败时 platform fatal |
| T2-02-08 disconnect 全部 runtime | unit | adapter disconnect 停止所有已创建 runtime |
| T2-02-09 account_id 日志 | unit | connect/disconnect/error 日志包含对应 `account_id` |

### T2-03 入站 account context 与授权策略

覆盖 WBS：W2-03

| 用例 | 类型 | 断言 |
| --- | --- | --- |
| T2-03-01 DM chat_id 带 account | unit | default account DM `source.chat_id == "default:EmpABC"` |
| T2-03-02 group chat_id 带 account | unit | staging group `source.chat_id == "staging:group/<seatalk_group_id>"` |
| T2-03-03 user_id 不带 account | unit | `source.user_id` 保持 email 或 employee code，不加 `default:` / `staging:` |
| T2-03-04 thread 单独承载 | unit | group thread id 写入 `source.thread_id`，不拼入 `source.chat_id` |
| T2-03-05 raw metadata | unit | `raw_message["seatalk_account_id"]` 等于 runtime account id |
| T2-03-06 session key 隔离 | unit | 同 sender 在 default/staging 下生成不同 Hermes session key |
| T2-03-07 DM allowlist | unit | `allow_from` 按 email 和 employee code 匹配，未命中则不 emit |
| T2-03-08 group raw allowlist | unit | `group_allow_from` 匹配 raw SeaTalk `group_id`，不是 `group/<id>` |
| T2-03-09 group sender allowlist | unit | `group_policy=open` 时仍按 `group_sender_allow_from` 限制 sender |
| T2-03-10 account policy 隔离 | unit | account A allow sender 不影响 account B |

### T2-04 Relay 多帐号 runtime

覆盖 WBS：W2-04

| 用例 | 类型 | 断言 |
| --- | --- | --- |
| T2-04-01 多 relay 启动 | integration | 两个 relay accounts 分别建立 WebSocket 连接 |
| T2-04-02 relay event 路由 | integration | default relay event 只进入 default dispatcher，staging 同理 |
| T2-04-03 relay payload app_id 校验 | unit | payload `app_id` 与 runtime `app_id` 不一致时丢弃并 warning |
| T2-04-04 auth_fail 隔离 | integration | 一个 account 收到 `auth_fail` 后标为永久失败，另一个继续 connected |
| T2-04-05 replaced 隔离 | integration | 一个 account 收到 `replaced` 后标为永久失败，其他 account 不受影响 |
| T2-04-06 heartbeat timeout 重连 | integration | 单 account heartbeat timeout 进入 retrying 并重连，不停止其他 account |
| T2-04-07 网络断开重连 | integration | mock server 断开单 account 连接，该 account backoff 重连 |
| T2-04-08 relay failure 不直接决定 platform fatal | integration | 所有 relay accounts auth_failed 时不直接按 relay 维度判定 platform fatal；platform fatal 由 W2-02 跨 relay/webhook runtime 聚合决定 |
| T2-04-09 日志 account_id | unit | relay auth/network/reconnect 日志包含 `account_id` |

### T2-05 Webhook challenge 与签名行为验证

覆盖 WBS：W2-05

| 用例 | 类型 | 断言 |
| --- | --- | --- |
| T2-05-01 challenge payload 实测 | HITL | 记录 SeaTalk `event_verification` payload 是否携带 `app_id` |
| T2-05-02 challenge 签名实测 | HITL | 确认 challenge 使用与普通事件相同的 Signature 校验规则 |
| T2-05-03 普通事件 app_id 实测 | HITL | 确认普通 message event 是否总携带 `app_id` |
| T2-05-04 shared endpoint 策略复核 | HITL | 基于实测确认先验签后解析的 shared endpoint 策略可用 |
| T2-05-05 TD 回填 | manual | 若协议与 TD 不一致，更新 TD §5.2 / §11 后再进入 W2-06 |

### T2-06 Webhook 多帐号 runtime

覆盖 WBS：W2-06

| 用例 | 类型 | 断言 |
| --- | --- | --- |
| T2-06-01 shared server 合并 | unit | 相同 `(host, port, path)` 的多个 accounts 只启动一个 server |
| T2-06-02 不同 endpoint 分离 | unit | 不同 path/port 的 accounts 启动不同 server |
| T2-06-03 先验签后解析 | integration | malformed JSON 但签名错误时返回 403，不进入 JSON parse error 路径 |
| T2-06-04 candidate secret 命中 | integration | 使用 staging secret 签名的请求路由到 staging runtime |
| T2-06-05 签名无匹配 | integration | 所有 candidate secrets 都不匹配时返回 403，不 dispatch |
| T2-06-06 app_id mismatch | integration | 签名匹配 account A 但 payload `app_id` 是 B 时返回 403 |
| T2-06-07 challenge 无 app_id | integration | 签名有效且 challenge payload 无 app_id 时仍返回 challenge |
| T2-06-08 普通事件缺 app_id | integration | 普通 message event 缺 app_id 时被拒绝 |
| T2-06-09 unknown app_id | integration | unknown app_id 返回 403 或 404，不泄露 account 枚举 |
| T2-06-10 dispatch account_id | integration | webhook dispatch 后 raw metadata 含正确 `seatalk_account_id` |

### T2-07 出站 account 选择与 Hermes patch

覆盖 WBS：W2-07

| 用例 | 类型 | 断言 |
| --- | --- | --- |
| T2-07-01 parser 无 prefix DM | unit | `EmpABC` 解析为默认 account resolution 的 DM target |
| T2-07-02 parser account DM | unit | `staging:EmpABC` 解析为 account `staging`、chat_id `EmpABC`、thread_id None |
| T2-07-03 parser group | unit | `group/<seatalk_group_id>` 解析为 group target |
| T2-07-04 parser account group thread | unit | `staging:group/<seatalk_group_id>:ThreadXYZ` 保留 account/group/thread |
| T2-07-05 prefix 先于 thread | unit | `staging:EmpABC` 不会被误解析为 `chat_id=staging, thread_id=EmpABC` |
| T2-07-06 metadata 优先 | unit | `metadata["seatalk_account_id"]` 优先于 target prefix |
| T2-07-07 default fallback | unit | 无 account prefix 时优先使用 `default` account |
| T2-07-08 first enabled fallback | unit | 无 default account 时使用按 account id 排序的第一个 enabled account |
| T2-07-09 send 使用目标 runtime | unit | send/send_typing/media send 调用解析出的 account runtime client |
| T2-07-10 home channel account | unit | `home_channel_account_id=staging` 返回 `staging:<home_channel>` |
| T2-07-11 cron account target | unit | cron SeaTalk target 使用 account-qualified target |
| T2-07-12 内置平台回归 | unit | Slack/Discord/Telegram 等原有 target parser 行为不变 |
| T2-07-13 get_chat_info account target | unit | `get_chat_info("staging:EmpABC")` 使用 staging account client，不把 `EmpABC` 误解析为 thread id |
| T2-07-14 SeaTalkTarget 默认 account_id | unit | `SeaTalkTarget(...)` 旧式四参数构造仍可用，`account_id` 默认为 None |
| T2-07-15 seatalk prefix 与 account prefix | unit | `seatalk:staging:EmpABC` 先剥离 `seatalk:`，再解析 account prefix 为 staging |

### T2-08 Setup wizard、文档与发布边界

覆盖 WBS：W2-08

| 用例 | 类型 | 断言 |
| --- | --- | --- |
| T2-08-01 wizard add account | unit | wizard 可创建 `accounts.<account_id>` 并写入 credentials/mode/policy |
| T2-08-02 wizard edit account | unit | wizard 编辑 account 不破坏其他 accounts |
| T2-08-03 wizard disable/remove | unit | disable/remove account 后配置结构正确 |
| T2-08-04 wizard home channel | unit | wizard 可设置 `home_channel_account_id` / `home_channel` / thread |
| T2-08-05 wizard 不写 env | unit | wizard 不写 SeaTalk secrets 到 `.env` |
| T2-08-06 wizard 无 pairing | unit | wizard 不展示 `dm_policy=pairing` |
| T2-08-07 README accounts 配置 | unit | README 展示 `platforms.seatalk.extra.accounts` 示例 |
| T2-08-08 README secrets 提醒 | unit | README 明确 `config.yaml` 包含 `app_secret` / `signing_secret` |
| T2-08-09 README group 格式 | unit | README 区分 `group_allow_from` raw id 与 `home_channel` target |
| T2-08-10 publish branch 内容 | integration | `scripts/publish-release.sh` 输出 publish branch 只含 runtime 文件和 README |
| T2-08-11 deploy 不覆盖 config | unit | deploy 脚本文档/逻辑不默认覆盖远端 `~/.hermes/config.yaml` |

### T2-09 自动化测试与回归收敛

覆盖 WBS：W2-09

| 用例 | 类型 | 断言 |
| --- | --- | --- |
| T2-09-01 全量离线 pytest | integration | 不设置真实 SeaTalk credentials 时核心 pytest 可通过 |
| T2-09-02 env 隔离 | unit | 测试间 env var 不互相污染，尤其是 internal allow-all env |
| T2-09-03 registry 隔离 | unit | platform registry 在测试间恢复 |
| T2-09-04 patch 隔离 | unit | runtime patch 测试不污染后续用例 |
| T2-09-05 Phase 1 default 回归 | integration | 单 default account 行为覆盖 Phase 1 主要 send/relay/webhook/auth 路径 |
| T2-09-06 batch 命令可用 | manual | 每个 batch 的 pytest 命令可执行并能生成 TR 输入 |
| T2-09-07 E2E runbook 更新 | manual | E2E runbook 包含多 account relay/webhook/出站/home channel 验证步骤 |

## 4. Batch 测试命令

### Batch 1：配置与注册基础

覆盖：W2-00、W2-01

```bash
uv run pytest tests/test_p2_config_accounts.py tests/test_w01_registration.py
```

### Batch 2：多 runtime 核心与入站身份

覆盖：W2-02、W2-03

```bash
uv run pytest tests/test_p2_runtime_accounts.py tests/test_p2_dispatcher_accounts.py
```

### Batch 3：Relay 多帐号

覆盖：W2-04

```bash
uv run pytest tests/test_p2_relay_accounts.py tests/test_w05_relay.py
```

### Batch 4：Webhook 风险验证与实现

覆盖：W2-05、W2-06

```bash
uv run pytest tests/test_p2_webhook_accounts.py tests/test_w04_webhook.py
```

W2-05 需要人工记录 SeaTalk challenge 实测结果，自动化命令只覆盖本地 mock。

### Batch 5：出站、设置与发布

覆盖：W2-07、W2-08

```bash
uv run pytest tests/test_p2_outbound_accounts.py tests/test_p2_setup_docs.py tests/test_w08_runtime_patch.py tests/test_w09_operations_docs.py
```

### Batch 6：测试与回归收敛

覆盖：W2-09

```bash
uv run pytest
```

## 5. 真实 SeaTalk 联调用例

| 用例 | 操作 | 通过标准 |
| --- | --- | --- |
| E2-01 多 relay accounts | 配置 default/staging 两个 relay accounts | 两个 account 均可接收消息，日志带 account_id |
| E2-02 relay auth failure 隔离 | 故意填错 staging credentials | staging 标为 auth_failed，default 仍可收发 |
| E2-03 relay reconnect 隔离 | 临时断开一个 account relay 连接 | 该 account 重连，其他 account 不断开 |
| E2-04 webhook challenge | 使用 SeaTalk webhook challenge 请求 | 签名有效时返回 challenge，记录 payload 形态 |
| E2-05 shared webhook endpoint | 两个 webhook accounts 共用 path | 请求按 signing secret / app_id 路由到正确 account |
| E2-06 DM account session | 同一用户分别向两个 account DM | Hermes session 不串联，`user_id` 不带 account prefix |
| E2-07 group sender policy | open group 中非 allowlist sender 触发 | agent 不执行，日志显示 sender_not_allowed |
| E2-08 outbound account target | 调用 `send_message` 到 `staging:group/<id>` | staging SeaTalk app 发送消息 |
| E2-09 home channel account | 配置 `home_channel_account_id=staging` 后触发 home send | 消息从 staging account 发出 |

真实联调需要 SeaTalk Bot App、relay/webhook 可达地址和测试用户/群，不纳入默认 CI。

## 6. 测试报告

Phase 2 使用一个滚动测试报告，每完成一个 WBS 任务后更新同一个 TR：

```text
docs/test/tr_hermes-seatalk-plugin_phase2_multi-account_zh.md
```

报告应包含：

- 已完成 WBS task。
- 自动化测试命令和结果。
- HITL 用例结果；无法执行时标记 PENDING 并说明依赖。
- Phase 1 回归测试结果。
- 失败分析和修复链接。
