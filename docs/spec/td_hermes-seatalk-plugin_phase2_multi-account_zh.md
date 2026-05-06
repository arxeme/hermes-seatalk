---
标题: Hermes SeaTalk Platform Plugin Phase 2 多帐号技术设计
状态: draft
更新日期: 2026-05-05
适用范围: hermes-seatalk (plugin 版)
作者: AI Agent Team
参考材料:
  - Hermes SeaTalk Platform Plugin 技术设计 (./td_hermes-seatalk-plugin_zh.md)
  - OpenClaw SeaTalk accounts 实现 (../../../openclaw-seatalk/src/accounts.ts)
  - OpenClaw SeaTalk config schema (../../../openclaw-seatalk/src/config-schema.ts)
  - OpenClaw SeaTalk relay/webhook runtime (../../../openclaw-seatalk/src/relay-client.ts, ../../../openclaw-seatalk/src/monitor.ts)
文档摘要: >
  定义 hermes-seatalk Phase 2 多帐号支持方案。目标是将单 SeaTalk Bot App 配置
  升级为 accounts 模型，每个 account 对应一个 SeaTalk App ID 绑定，并将 app secret /
  signing secret 作为 account 配置直接保存在 config.yaml 中。
---

# Hermes SeaTalk Plugin Phase 2：多帐号技术设计

## 1. 背景与设计约束

Phase 1 的 hermes-seatalk 只支持一个 SeaTalk Bot App。Phase 2 需要将配置模型
升级为 accounts-only：所有 SeaTalk runtime 配置都必须位于
`platforms.seatalk.extra.accounts`。

Phase 2 需要与 `openclaw-seatalk` 的多帐号模型对齐：

- 新增 `accounts` 层，每个 account 代表一个 SeaTalk App ID 绑定。
- 每个 account 拥有独立 credentials、gateway mode、relay/webhook 配置和授权策略。
- app secret / signing secret 不走 `.env`，而是直接写入 `config.yaml`。
- Hermes 仍然只注册一个 platform：`seatalk`。多帐号是 plugin 内部 runtime 能力，
  不是多个 Hermes platform。

`extra` 这一层保持不变。原因是 Hermes 的 `platforms.seatalk` 先属于通用
`PlatformConfig`；plugin 私有 schema 必须放在 `extra` 中，才能不修改
hermes-agent core。OpenClaw 的 `channels.seatalk.accounts` 与 Hermes 的
`platforms.seatalk.extra.accounts` 语义对齐，但层级不同。

本文只定义 Phase 2 设计，不直接实施。

## 2. 目标与非目标

### 2.1 目标

1. 支持多个 SeaTalk Bot App 同时接入 Hermes gateway。
2. 支持每个 account 独立配置：
   - `app_id`
   - `app_secret`
   - `signing_secret`
   - `enabled`
   - `mode`
   - `relay_url`
   - `webhook_host` / `webhook_port` / `webhook_path`
   - `dm_policy`
   - `allow_from`
   - `group_policy`
   - `group_allow_from`
   - `group_sender_allow_from`
   - `processing_indicator`
   - `media_allow_hosts`
   - `outbound_coalescing`
3. 与 OpenClaw 配置语义保持一致，但保留 Hermes Python/YAML 的 snake_case 风格。
4. 明确入站事件如何路由到正确 account。
5. 明确出站消息如何选择 account。
6. 移除用户可见的 `SEATALK_APP_SECRET` / `SEATALK_SIGNING_SECRET` `.env` 依赖。

### 2.2 非目标

1. 不把 SeaTalk 拆成多个 Hermes platform，例如 `seatalk-prod`、`seatalk-staging`。
2. 不在 Phase 2 实现 OpenClaw 的 `tools` 子配置；Hermes 当前没有等价的 SeaTalk
   tool schema。
3. 不在 Phase 2 支持 `dm_policy=pairing`。多帐号 pairing 的 account 边界不清楚，
   Phase 2 只支持 `allowlist` 和 `open`。
4. 不提供任何配置迁移流程；Phase 2 只定义最终 accounts-only 配置。
5. 不支持 `platforms.seatalk.accounts` 直挂配置；SeaTalk 私有配置必须位于
   `platforms.seatalk.extra`。

## 3. 配置模型

### 3.1 OpenClaw 对齐关系

OpenClaw 使用 camelCase：

```json5
{
  "seatalk": {
    "accounts": {
      "default": {
        "enabled": true,
        "appId": "your_app_id",
        "appSecret": "your_app_secret",
        "signingSecret": "your_signing_secret",
        "mode": "relay",
        "relayUrl": "wss://relay.example.com/seatalk/ws",
        "dmPolicy": "allowlist",
        "allowFrom": ["alice@example.com"],
        "groupPolicy": "open",
        "groupSenderAllowFrom": ["alice@example.com"],
        "processingIndicator": "typing"
      }
    }
  }
}
```

Hermes plugin 使用 snake_case，并保留 `extra` 作为 plugin 私有配置边界：

```yaml
platforms:
  seatalk:
    enabled: true
    extra:
      accounts:
        default:
          enabled: true
          app_id: your_app_id
          app_secret: your_app_secret
          signing_secret: your_signing_secret
          mode: relay
          relay_url: wss://relay.example.com/seatalk/ws
          dm_policy: allowlist
          allow_from:
            - alice@example.com
          group_policy: open
          group_sender_allow_from:
            - alice@example.com
          processing_indicator: typing
```

字段映射：

| OpenClaw | Hermes Phase 2 | 说明 |
|---|---|---|
| `accounts` | `accounts` | account id -> account config |
| `enabled` | `enabled` | 顶层和 account 均支持；任一为 false 则 account disabled |
| `appId` | `app_id` | SeaTalk App ID |
| `appSecret` | `app_secret` | 直接保存在 `config.yaml` |
| `signingSecret` | `signing_secret` | 直接保存在 `config.yaml` |
| `mode` | `mode` | `webhook` / `relay` |
| `relayUrl` | `relay_url` | relay mode 必填 |
| `webhookPort` | `webhook_port` | webhook mode 使用，默认 8080 |
| `webhookPath` | `webhook_path` | 默认 `/callback` |
| `dmPolicy` | `dm_policy` | `open` / `allowlist`；Phase 2 不支持 `pairing` |
| `allowFrom` | `allow_from` | DM sender allowlist |
| `groupPolicy` | `group_policy` | `disabled` / `allowlist` / `open` |
| `groupAllowFrom` | `group_allow_from` | SeaTalk payload 中的 `group_id` 原值，按 API 返回值原样配置；不要添加 Hermes target 前缀 `group/` |
| `groupSenderAllowFrom` | `group_sender_allow_from` | group 内 sender allowlist |
| `processingIndicator` | `processing_indicator` | `typing` / `off` |
| `mediaAllowHosts` | `media_allow_hosts` | 入站媒体允许域名 |
| `outboundCoalescing` | `outbound_coalescing` | 出站合并 |

### 3.2 顶层默认值与 account override

保留 OpenClaw 的继承模型：`platforms.seatalk.extra` 顶层字段作为 account 默认值，
`accounts.<account_id>` 覆盖顶层字段。

示例：

```yaml
platforms:
  seatalk:
    enabled: true
    extra:
      dm_policy: allowlist
      allow_from:
        - alice@example.com
      group_policy: disabled
      processing_indicator: typing
      accounts:
        default:
          enabled: true
          app_id: prod_app_id
          app_secret: prod_app_secret
          signing_secret: prod_signing_secret
          mode: relay
          relay_url: wss://relay.example.com/ws
          group_policy: open
          group_sender_allow_from:
            - alice@example.com
        staging:
          enabled: true
          app_id: staging_app_id
          app_secret: staging_app_secret
          signing_secret: staging_signing_secret
          mode: webhook
          webhook_port: 8081
```

解析规则：

1. `accounts` 必须存在且非空。
2. 顶层 `enabled=false` 禁用整个 SeaTalk platform。
3. account `enabled=false` 只禁用该 account。
4. account 配置 = 顶层默认字段去掉 `accounts` 后，与 account 字段 shallow merge。
5. account id 为空字符串非法。
6. account id 必须匹配 `^[a-z0-9][a-z0-9_.-]*$`，用于日志、metadata 和 target
   前缀；不允许冒号、斜杠、空格和大写字符。

## 4. 运行时架构决策

Phase 2 已决策采用**单 Adapter 内部管理多个 AccountRuntime**的方案。
Hermes 仍然只看到一个 `seatalk` platform；多帐号能力完全封装在
hermes-seatalk plugin 内部。

备选方案与取舍记录见
[TDR: Hermes SeaTalk Phase 2 多帐号运行时架构决策](./tdr_hermes-seatalk-plugin_phase2_multi-account-runtime_zh.md)。

### 4.1 AccountRuntime 模型

接口形态：

```python
@dataclass
class SeaTalkAccountConfig:
    account_id: str
    enabled: bool
    app_id: str
    app_secret: str
    signing_secret: str
    mode: str
    relay_url: str
    webhook_host: str
    webhook_port: int
    webhook_path: str
    policy: SeaTalkPolicy

@dataclass
class SeaTalkAccountRuntime:
    config: SeaTalkAccountConfig
    client: SeaTalkOpenAPIClient
    dispatcher: SeaTalkEventDispatcher
    relay_client: SeaTalkRelayClient | None
```

`SeaTalkAdapter` 负责：

- 解析所有 enabled/configured accounts。
- 为每个 account 创建 client、dispatcher、relay client。
- 在 `connect()` 中启动全部 account runtime。
- 在 `disconnect()` 中停止全部 runtime。
- 在 `send()` 中根据 target/metadata 选择 account。

### 4.2 设计约束

- 不动态注册多个 Hermes platform。
- 不要求 hermes-agent core 识别 account。
- 不把 account id 放入 platform name。
- 所有 account runtime 必须共享同一个 plugin 注册入口 `register(ctx)`。
- account runtime 可以各自拥有 client、dispatcher、relay client 和 coalescer。
- Webhook server 可以按 `(host, port, path)` 合并，但 dispatch 必须落到具体 account runtime。

## 5. 入站事件路由

### 5.1 Relay mode

每个 relay account 建立一个 `SeaTalkRelayClient`：

```text
account.default -> relay connection authenticated by default app credentials
account.staging -> relay connection authenticated by staging app credentials
```

relay 收到 event 后直接调用该 account runtime 的 dispatcher，因此不需要再根据
`payload.app_id` 查表。仍应校验：

- payload `app_id` 若存在，必须等于 runtime `app_id`，否则丢弃并记录 warning。
- dispatcher 仍可使用现有 `{app_id}:{event_id}` dedup key；每个 account runtime
  拥有独立 dispatcher，且 enabled accounts 的 `app_id` 不允许重复，因此不需要额外
  在 dedup key 中加入 `account_id`。

### 5.2 Webhook mode

当前 `SeaTalkWebhookServer` 只有一个 `signing_secret`，Phase 2 需要改为 resolver：

```python
SigningSecretResolver = Callable[[dict[str, Any]], str | None]
```

处理顺序：

1. 读取 raw body。
2. 对该 `(host, port, path)` 下所有 enabled webhook account 的 `signing_secret`
   逐一验证 Signature。
3. 若没有任何 account 验签通过，返回 403。
4. 验签通过后解析 JSON；解析失败直接 400。
5. 若 payload 中有 `app_id`，必须与验签通过的 account 的 `app_id` 一致，否则返回
   403。
6. `event_verification` challenge 若没有 `app_id`，仍可直接用验签通过的 account
   返回 challenge。
7. 普通事件若缺失 `app_id`，返回 400 或 403，推荐 403，避免泄露路由规则。
8. 验证通过后 dispatch 到该 account runtime。

这样保持 Phase 1 的安全顺序：`read body -> verify signature -> parse JSON`。
共享 webhook endpoint 不依赖 challenge payload 是否携带 `app_id`。`SeaTalkWebhookServer`
当前已通过 `MAX_BODY_BYTES = 1MB` / aiohttp `client_max_size` 限制请求大小；
Phase 2 必须保留该限制。

server 绑定策略：

- 相同 `(host, port, path)` 的多个 webhook account 共享一个 server。
- 不同 `(host, port, path)` 创建多个 server。
- 若同一个 `app_id` 出现在多个 enabled accounts，应视为配置错误。

### 5.3 SessionSource 与 raw metadata

Hermes `SessionSource.platform` 仍是 `seatalk`。Hermes session key 当前按
`platform/chat_id/thread/user` 维度构造，不包含 `raw_message` metadata，因此
Phase 2 必须把 account id 放入 `source.chat_id`，避免不同 account 的相同 DM
employee code 或相同 group id 共用同一个 session。

决策：

- `source.chat_id` 采用 account-qualified Hermes SeaTalk 目标格式：
  `<account_id>:<seatalk_target>`。
- DM 的 `<seatalk_target>` 为 employee code 或 email fallback 后的现有 DM target。
- group 的 `<seatalk_target>` 为 `group/<seatalk_group_id>`。这里的 `group/` 是
  Hermes target wrapper，`<seatalk_group_id>` 是 SeaTalk payload 中的 `group_id`
  原值。这个值不同于 `group_allow_from` 配置项；`group_allow_from` 只写
  `<seatalk_group_id>` 本身。
- `source.chat_id` 示例：
  - `default:EmpABC`
  - `staging:EmpABC`
  - `default:group/<seatalk_group_id>`
  - `staging:group/<seatalk_group_id>`
- `raw_message` 增加 `seatalk_account_id`。
- `source.user_id` 不加 account prefix；session key 的 account 维度已由
  `source.chat_id` 承载，不需要在 `user_id` 中重复。
- `source.message_id` 仍用 SeaTalk message id。
- `source.thread_id` 继续单独承载 SeaTalk thread id，不拼进 `source.chat_id`。

## 6. 出站目标与 Account 选择

多 account 后，`send_message(target="seatalk")` 和
`send("group/<seatalk_group_id>")`
必须有确定 account。

### 6.1 Account 选择顺序

1. `metadata["seatalk_account_id"]`
2. target 前缀：`<account_id>:<seatalk_target>`
3. `default` account
4. 第一个 enabled/configured account（按 account id 排序）

### 6.2 Target 格式

保持原有 target 格式，同时新增 account 前缀：

| 输入 | account | SeaTalk target |
|---|---|---|
| `EmpABC` | default resolution | `EmpABC` |
| `alice@example.com` | default resolution | `alice@example.com` |
| `group/<seatalk_group_id>` | default resolution | `group/<seatalk_group_id>` |
| `staging:EmpABC` | `staging` | `EmpABC` |
| `staging:group/<seatalk_group_id>` | `staging` | `group/<seatalk_group_id>` |
| `staging:group/<seatalk_group_id>:ThreadXYZ` | `staging` | `group/<seatalk_group_id>:ThreadXYZ` |

注意：当前 target parser 已使用冒号表达 thread id。实施时必须避免 account prefix
和 thread id 冲突。推荐解析规则：

- 若第一个 `:` 之前的 token 是已配置 account id，则它是 account prefix。
- 否则保持 Phase 1 解析逻辑，冒号只表示 thread id。
- account prefix 必须在现有 group/email/thread 解析之前剥离；不能先调用当前
  `_split_optional_thread()`，否则 `staging:EmpABC` 会被误解析为
  `chat_id=staging, thread_id=EmpABC`。
- `parse_seatalk_target()` 需要新增 `known_accounts: set[str] | None` 输入，并在返回值
  中携带 `account_id: str | None`；`SeaTalkAdapter._resolve_target()`、
  `_patch_send_message_tool()` 和 `_seatalk_send_to_platform()` 都必须传入当前
  enabled account id 集合。

### 6.3 Home Channel

Home channel 不写入 `platforms.seatalk.extra`，回归 Hermes 原生 env 机制：

```dotenv
SEATALK_HOME_CHANNEL=staging:group/<seatalk_group_id>
SEATALK_HOME_CHANNEL_THREAD_ID=
SEATALK_HOME_CHANNEL_NAME=SeaTalk Home
```

`SEATALK_HOME_CHANNEL` 是 Hermes 目标配置，所以 group 需要写
`group/<seatalk_group_id>`；这和 `group_allow_from` 的 raw `group_id` 配置不同。
多 account 场景下，用 account-qualified target，例如
`staging:group/<seatalk_group_id>`。这样 cron、home channel 和普通
`send_message` 仍然走同一套 account prefix 解析逻辑，但配置来源遵循 Hermes
标准 `.env` 设计。

## 7. 授权与安全

### 7.1 Plugin 内部授权继续作为 source of truth

Phase 2 引入 plugin 内部 allow-all env，用于让 Hermes core 的 platform 级授权闸门
与 SeaTalk dispatcher 内部授权协同；真正的 SeaTalk 授权由 dispatcher 在进入
Hermes 前完成。

Phase 2 继续采用此策略：

- 不写用户可见 `SEATALK_ALLOW_ALL_USERS` / `GATEWAY_ALLOW_ALL_USERS`。
- 不依赖 `.env` allowlist。
- `register()` 在 plugin 内部设置 `HERMES_SEATALK_ALLOW_ALL=true`，并通过
  `allow_all_env=HERMES_SEATALK_ALLOW_ALL` 注册 platform；不传
  `allowed_users_env`。这个内部 env 只用于通过 Hermes core 的 platform 级授权闸门，
  不是用户可配置授权策略，也不写入用户 `.env`。
- 每个 account 独立执行 `dm_policy` / `allow_from` / `group_policy` /
  `group_sender_allow_from`。

### 7.2 Credentials

Phase 2 将 credentials 直接放入 `config.yaml`。这与 OpenClaw 配置一致，但需要明确：

- README 和 setup wizard 必须提示 `config.yaml` 包含 secrets。
- deploy 脚本不得默认覆盖远端 `config.yaml`。
- 文档和日志不得打印 `app_secret` / `signing_secret`。
- `SeaTalkOpenAPIClient` 的 `log_secrets` 应包含所有 account secrets。

### 7.3 配置校验

每个 enabled account 必须满足：

- `app_id`、`app_secret`、`signing_secret` 非空。
- `mode` 是 `webhook` 或 `relay`。
- relay account 必须有 `relay_url`。
- webhook account 必须有合法 `webhook_port` 和 `webhook_path`。
- policy 枚举值合法。
- `dm_policy` 只允许 `allowlist` / `open`；`pairing` 在 Phase 2 中非法。
- `group_allow_from` 中的值不得以 `group/` 开头；该字段只接受 SeaTalk payload
  中的 raw `group_id`。若发现 `group/<id>` 形式，配置校验失败并给出明确错误。

整体配置必须满足：

- 至少一个 enabled/configured account。
- enabled accounts 的 `app_id` 不重复。
- 同一 `(webhook_host, webhook_port, webhook_path)` 下 app_id 可不同并共享 server；
  同 app_id 不可重复。
- 配置校验采用 all-or-nothing 语义：任一 enabled account 配置非法，整体配置失败。
- runtime 启动采用 per-account 独立语义：
  - auth failure 只标记该 account 永久失败，记录带 `account_id` 的 error 日志，不影响
    其他 account。
  - 网络失败、连接超时、relay 暂时不可达由对应 runtime/relay client 独立重连，不让
    其他 account 断开。
  - 仅当所有 enabled accounts 均进入 auth failure 或不可启动的永久失败状态时，整个
    SeaTalk platform 标为 fatal。

## 8. Setup Wizard 设计

Phase 2 setup wizard 以 account 为配置单位：

1. 选择动作：
   - add account
   - edit account
   - disable account
   - remove account
   - set home channel
2. account id：
   - 默认 `default`
   - 校验字符集
3. credentials：
   - app id
   - app secret
   - signing secret
4. mode：
   - relay -> relay url
   - webhook -> host/port/path
5. auth policy：
   - dm policy + allow_from
   - group policy + group_allow_from / group_sender_allow_from
6. processing/media/outbound defaults

Wizard 不写 `.env`，只通过 add/edit account 直接写入
`platforms.seatalk.extra.accounts.<account_id>`。

## 9. 实施切片

### Slice 1：配置解析与模型

- 新增 account dataclass。
- 新增 `_accounts_from_extra(extra)`。
- 新增 `_merge_account_config(base, account)`。
- `_validate_seatalk_config()` 改为校验 accounts。
- `REQUIRED_ENV = []`；Phase 2 不再让 Hermes setup/status 通过 `.env` 检查
  SeaTalk credentials。
- `check_seatalk_requirements()` 只校验 Python 依赖，例如 `aiohttp` 可导入；不读取
  `.env`，也不读取 `config.yaml`。
- `validate_config=_validate_seatalk_config` 负责完整校验
  `platforms.seatalk.extra.accounts`：至少一个 enabled/configured account、每个
  enabled account credentials 完整、mode/policy/webhook/relay 配置合法。
- `register()` 设置内部 `HERMES_SEATALK_ALLOW_ALL=true`，并以
  `allow_all_env=HERMES_SEATALK_ALLOW_ALL` 注册 platform，避免 Hermes core 在
  dispatcher 授权之后再次按空 allowlist 拦截消息。
- 顶层 account 外 credentials 不参与运行时配置解析。

### Slice 2：单 Adapter 多 runtime

- `SeaTalkAdapter` 引入 `self.accounts` / `self._runtimes`。
- 每个 runtime 拥有独立 client、dispatcher、coalescer。
- `SeaTalkAdapter` 在创建 client 前收集所有 enabled account 的 `app_secret` 和
  `signing_secret`，去重后注入每个 `SeaTalkOpenAPIClient.log_secrets`，确保任一
  account 的 secret 都不会在其他 runtime 的日志路径泄露。
- `connect()` / `disconnect()` 管理所有 runtimes。
- `connect()` 使用 per-account 独立语义：尽量启动所有 enabled runtimes。
- runtime 启动结果需要保存在 account 级状态中，例如 `running`、`auth_failed`、
  `retrying`、`stopped`、`last_error`。
- Hermes 仍只有一个 `seatalk` platform status surface，因此 adapter 聚合状态：
  至少一个 account running/retrying 时，platform 不进入 fatal；所有 enabled accounts
  均永久失败时，platform fatal。
- 所有 runtime connect/disconnect/error 日志必须携带 `account_id`。

### Slice 3：Relay 多帐号

- 每个 relay account 启动一个 relay client。
- relay dispatch 绑定 account runtime。
- auth failed / connected 状态按 account 记录并聚合到 platform。
- relay 网络错误和 heartbeat timeout 由各 account 的 `SeaTalkRelayClient` 独立重连；
  不影响其他 account。
- relay `auth_fail` 或 `replaced` 标记该 account 永久失败，不影响其他 account。

### Slice 4：Webhook 多帐号

- `SeaTalkWebhookServer` 支持 signing secret resolver 和 account dispatch resolver。
- 按 `(host, port, path)` 合并 server。
- 对 endpoint 下所有 candidate signing secrets 先验签，验签通过后再解析 JSON。
- 按验签匹配的 account 和 payload `app_id` 路由 account；challenge payload 没有
  `app_id` 时仍可返回 challenge。

### Slice 5：出站 account 选择

- target parser 支持 account prefix，且 prefix 解析必须发生在 group/email/thread
  解析之前。
- `SeaTalkTarget` 增加 `account_id` 字段；所有 parser 调用点传入
  `known_accounts`。
- `send()` / `send_typing()` / media send 使用目标 account runtime。
- home channel 和 cron scheduler patch 读取 `SEATALK_HOME_CHANNEL*` env，并支持
  account-qualified target。

### Slice 6：setup wizard、docs、tests

- Wizard 改为 account 管理。
- README / env.example 改为 accounts 配置。
- 测试覆盖 accounts 解析、relay/webhook routing、sender policy、出站 target account。

## 10. 测试计划

### Unit

- `accounts` 缺失、空、非法类型时校验失败。
- `accounts.default` relay 配置完整时校验成功。
- 多 account 继承顶层默认值。
- account override 覆盖顶层默认值。
- `.env` secrets 不参与校验。
- `REQUIRED_ENV` 为空；setup/status 不再要求 `SEATALK_APP_SECRET` /
  `SEATALK_SIGNING_SECRET`。
- `check_seatalk_requirements()` 只检查依赖，不读取 `config.yaml`。
- 重复 app_id 被拒绝。
- relay mode 缺 relay_url 被拒绝。
- webhook port/path 非法被拒绝。
- account id 非法被拒绝。
- account id 含大写、冒号、斜杠或空格被拒绝。
- `dm_policy=pairing` 被拒绝。
- `group_allow_from` 中出现 `group/<id>` 被拒绝。
- `register()` 设置内部 `HERMES_SEATALK_ALLOW_ALL=true`，注册
  `allow_all_env=HERMES_SEATALK_ALLOW_ALL`，且不注册 `allowed_users_env`。
- 任一 enabled account 配置非法时，整体配置失败。
- 单个 runtime auth failure 不停止其他 account。
- relay 网络错误或 heartbeat timeout 进入该 account 的 retrying 状态，不停止其他
  account。
- 所有 enabled accounts 均永久失败时，platform fatal。
- runtime connect/disconnect/error 日志包含 `account_id`。

### Dispatcher

- DM allowlist 按 account 生效。
- group open + group_sender_allow_from 按 account 生效。
- 不同 account 相同 event id 不互相 dedup；通过独立 dispatcher 和唯一 app_id
  保证，不要求修改 dedup key 格式。

### Relay

- 两个 relay accounts 各自创建连接。
- relay event 进入正确 account dispatcher。
- relay payload app_id 不匹配 runtime app_id 时被丢弃。
- 一个 relay account auth_fail 时，另一个 account 继续运行。
- 一个 relay account heartbeat timeout / 网络断开时，该 account 进入重连，不影响
  其他 account。

### Webhook

- 多 account 共享同一个 webhook endpoint。
- 签名验证发生在 JSON 解析之前。
- challenge payload 不带 app_id 时，仍可通过匹配到的 signing secret 返回 challenge。
- 普通事件缺失 app_id 被拒绝。
- 签名错误返回 403。
- unknown app_id 返回 403 或 404，推荐 403，避免泄露 app id 枚举。

### Outbound

- `staging:group/<seatalk_group_id>` 使用 staging client。
- `staging:EmpABC` 不会被误解析为 `chat_id=staging, thread_id=EmpABC`。
- 无 account prefix 时使用 default account。
- `metadata["seatalk_account_id"]` 优先级高于 target prefix。
- home channel 和 cron delivery 通过 `SEATALK_HOME_CHANNEL` account-qualified
  target 指定 account。

## 11. 风险与待确认问题

1. **SeaTalk webhook challenge 实测**：
   当前设计不依赖 challenge payload 携带 `app_id`，但 Slice 4 前仍需要用 SeaTalk
   实机或官方文档确认 challenge payload 形态，补齐集成测试。

2. **GitHub publish branch 发布注意事项**：
   Phase 2 文档和测试留在 `main`；安装所需 runtime 文件和 README 需要通过
   `scripts/publish-release.sh` 发布到 `publish` 分支，保证
   `hermes plugins install arxeme/hermes-seatalk --enable` 安装到最新 runtime 文件。

## 12. 推荐结论

采用“单 Hermes platform + plugin 内部多 AccountRuntime”的设计。

配置上与 OpenClaw 保持语义一致，但使用 snake_case：

```yaml
platforms:
  seatalk:
    enabled: true
    extra:
      accounts:
        default:
          enabled: true
          app_id: your_app_id
          app_secret: your_app_secret
          signing_secret: your_signing_secret
          mode: relay
          relay_url: wss://relay.example.com/seatalk/ws
          dm_policy: allowlist
          allow_from:
            - alice@example.com
          group_policy: open
          group_sender_allow_from:
            - alice@example.com
          processing_indicator: typing
```

确认本文档后，实施应按第 9 节切片推进，优先完成配置解析和 relay 多帐号，再实现
webhook 多帐号。
