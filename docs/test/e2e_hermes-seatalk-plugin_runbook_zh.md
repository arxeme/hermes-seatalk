# Hermes SeaTalk Plugin 真实联调 Runbook

更新时间：2026-05-04

## 1. 目的

本文用于记录 W-11 真实 SeaTalk 联调验证。W-11 依赖真实 SeaTalk Bot App、真实用户、真实群和可达的 webhook 或 relay 通道，因此不能在离线 pytest 中自动完成。

本文件只记录可复现步骤和结果摘要，不记录 `SEATALK_APP_SECRET`、`SEATALK_SIGNING_SECRET`、access token 或任何截图中的 secret。

## 2. 前置条件

| 项目 | 要求 | 当前记录 |
| --- | --- | --- |
| Hermes 版本 | 已安装支持 user plugin 的官方新版本 | PENDING |
| Plugin 安装路径 | `~/.hermes/plugins/seatalk` 或等价用户 plugin 目录 | PENDING |
| Plugin enable | `hermes plugins enable seatalk-platform` 已执行 | PENDING |
| Gateway restart | enable 和配置变更后已重启 gateway | PENDING |
| SeaTalk Bot App | 已创建 Bot App，并配置 App ID、App Secret、Signing Secret | PENDING |
| 入站模式 | `relay` 或 `webhook` 至少一种真实可用 | PENDING |
| 授权用户 | 至少一个 allowlist 内用户和一个 allowlist 外用户 | PENDING |
| 授权群 | 至少一个 allowlist 内群和一个 allowlist 外群 | PENDING |

## 3. 配置摘要模板

| 配置项 | 记录方式 |
| --- | --- |
| `SEATALK_APP_ID` | 记录前后 3 位或内部 Bot App 名称，不记录完整 secret |
| `SEATALK_APP_SECRET` | 只记录已配置，不记录值 |
| `SEATALK_SIGNING_SECRET` | 只记录已配置，不记录值 |
| `SEATALK_MODE` | `relay` 或 `webhook` |
| `SEATALK_RELAY_URL` | relay 模式记录域名和 path，可遮蔽 token/query |
| `SEATALK_WEBHOOK_*` | webhook 模式记录外部 callback URL 与本地 host/port/path |
| `SEATALK_ALLOWED_USERS` | 记录测试用户类别，不记录完整用户清单 |
| `SEATALK_GROUP_ALLOWED_USERS` | 记录测试群类别，不记录敏感群名 |
| `SEATALK_HOME_CHANNEL` | 记录是否为 DM/group/thread，必要时遮蔽 id |

## 4. 执行步骤

### E-01 Bot App 配置

1. 安装并启用 plugin。
2. 运行 `hermes gateway setup`。
3. 在 TUI 中确认 SeaTalk 出现在 messaging platform 菜单。
4. 录入 common credentials。
5. 选择 `relay` 或 `webhook` 并录入对应模式的配置。
6. 重启 gateway。
7. 执行 `hermes gateway status`。

预期结果：

- SeaTalk 显示 configured。
- `is_connected` 静态语义与 credentials 完整性一致。
- runtime health 通过 gateway 运行日志或 status health 记录观察。

### E-02 用户私聊入站

1. 授权用户向 bot 发送文本。
2. 查看 Hermes gateway 日志和 agent 输入。
3. 记录 session key、`source.user_id`、`source.user_id_alt`。

预期结果：

- agent 收到输入并产生响应。
- 有 email 时 `source.user_id` 为 email。
- 无 email 时 fallback 到 employee code，并保留 `source.user_id_alt`。

### E-03 群聊入站

1. 在授权群中由授权用户发送文本。
2. 如配置 `SEATALK_REQUIRE_MENTION=true`，使用 @bot 方式触发。
3. 查看 channel 和 thread metadata。

预期结果：

- 消息进入正确 session。
- channel id 为 `group/<id>` 格式。
- thread id 与 SeaTalk 事件一致。

### E-04 出站工具调用

1. 在 Hermes 中触发：

```bash
send_message(target="seatalk", message="hello from hermes")
```

2. 或指定目标：

```bash
send_message(target="seatalk:group/<id>:<thread_id>", message="hello thread")
```

预期结果：

- SeaTalk 客户端收到文本。
- thread 目标不被误解析为 chat id。
- gateway 日志无 `No live SeaTalk adapter`。

### E-05 Home Channel

1. 配置 `SEATALK_HOME_CHANNEL`。
2. 如需 thread，配置 `SEATALK_HOME_CHANNEL_THREAD_ID`。
3. 触发 cron 或 home channel 发送。

预期结果：

- 消息到达 home channel。
- thread id 行为符合配置。

### E-06 未授权用户

1. 非 allowlist 用户向 bot 或授权群发送消息。
2. 查看 agent 是否执行。
3. 查看拒绝日志。

预期结果：

- agent 不执行。
- 日志记录拒绝原因。
- 日志不泄漏 app secret、access token、signing secret 或 sender email 明文。

### E-07 未授权群

1. 授权用户在非 `SEATALK_GROUP_ALLOWED_USERS` 群内发送消息。
2. 查看 dispatcher 预过滤日志。

预期结果：

- agent 不执行。
- 日志记录 channel 拒绝原因。
- 该拒绝发生在用户鉴权之前。

### E-08 文件或图片

1. 授权用户发送或转发图片。
2. 授权用户发送或转发普通文件。
3. 触发出站图片或文件发送。

预期结果：

- 入站 metadata 包含附件信息。
- 下载失败时文本和降级占位仍进入 agent。
- 出站 native image/file payload 可发送，或给出明确降级错误。

### E-09 Relay/Webhook Runtime Health

Relay 模式：

1. 停止 relay service 或断开 gateway 到 relay 的网络。
2. 观察 gateway runtime health/log。
3. 恢复 relay service。

Webhook 模式：

1. 停止 callback 可达性或临时移除外部 callback。
2. 观察 webhook server 和 SeaTalk 事件投递失败记录。
3. 恢复 callback。

预期结果：

- 状态变化可观察。
- 恢复后可继续收发。
- `is_connected` 不被 runtime health 语义污染。

## 5. 结果记录表

| 用例 | 模式 | 结果 | 证据摘要 | 问题链接 |
| --- | --- | --- | --- | --- |
| E-01 Bot App 配置 | PENDING | PENDING | PENDING | PENDING |
| E-02 用户私聊入站 | PENDING | PENDING | PENDING | PENDING |
| E-03 群聊入站 | PENDING | PENDING | PENDING | PENDING |
| E-04 出站工具调用 | PENDING | PENDING | PENDING | PENDING |
| E-05 Home Channel | PENDING | PENDING | PENDING | PENDING |
| E-06 未授权用户 | PENDING | PENDING | PENDING | PENDING |
| E-07 未授权群 | PENDING | PENDING | PENDING | PENDING |
| E-08 文件或图片 | PENDING | PENDING | PENDING | PENDING |
| E-09 Runtime Health | PENDING | PENDING | PENDING | PENDING |

## 6. 问题回流

真实联调发现的问题应回流到以下位置：

| 问题类型 | 回流位置 |
| --- | --- |
| TD 设计偏差 | `docs/spec/td_hermes-seatalk-plugin_zh.md` |
| WBS 范围或拆分问题 | `docs/spec/wbs_hermes-seatalk-plugin_zh.md` |
| TP 缺失用例 | `docs/test/tp_hermes-seatalk-plugin_zh.md` |
| 自动化可覆盖的缺陷 | `tests/` |
| 仅真实环境可复现的问题 | 本 runbook 的结果记录表和独立 issue |
