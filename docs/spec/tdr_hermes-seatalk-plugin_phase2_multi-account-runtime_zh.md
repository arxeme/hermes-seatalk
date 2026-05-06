---
标题: Hermes SeaTalk Phase 2 多帐号运行时架构决策
状态: accepted
更新日期: 2026-05-05
适用范围: hermes-seatalk Phase 2 多帐号
作者: AI Agent Team
关联设计:
  - Hermes SeaTalk Platform Plugin Phase 2 多帐号技术设计 (./td_hermes-seatalk-plugin_phase2_multi-account_zh.md)
参考材料:
  - OpenClaw SeaTalk accounts 实现 (../../../openclaw-seatalk/src/accounts.ts)
  - OpenClaw SeaTalk relay/webhook runtime (../../../openclaw-seatalk/src/relay-client.ts, ../../../openclaw-seatalk/src/monitor.ts)
文档摘要: >
  记录 hermes-seatalk Phase 2 多帐号运行时架构的技术决策。结论是采用
  单 Hermes platform + plugin 内部多 AccountRuntime，不动态注册多个 Hermes platform。
---

# TDR: Hermes SeaTalk Phase 2 多帐号运行时架构决策

## 1. 决策

采用**方案 A：单 Adapter 内部管理多个 AccountRuntime**。

Hermes 仍然只注册一个 platform：`seatalk`。每个 SeaTalk account 在 plugin 内部
解析成一个 `SeaTalkAccountRuntime`，runtime 独立持有 client、dispatcher、relay
client / webhook routing state 和 outbound coalescer。

## 2. 背景

Phase 2 需要支持：

- 一个 Hermes gateway 同时连接多个 SeaTalk Bot App。
- 每个 account 独立配置 credentials、mode、relay/webhook endpoint 和授权策略。
- 配置语义与 OpenClaw SeaTalk 的 `accounts` 模型一致。
- 不修改 hermes-agent core。

Hermes plugin 注册模型天然以 platform 为单位。SeaTalk 多帐号是 SeaTalk plugin 的
内部能力，不应泄漏成多个 Hermes platform。

## 3. 备选方案

### 3.1 方案 A：单 Adapter 内部管理多个 AccountRuntime

接口形态：

```python
class SeaTalkAdapter(BasePlatformAdapter):
    accounts: dict[str, SeaTalkAccountConfig]
    runtimes: dict[str, SeaTalkAccountRuntime]
```

每个 runtime：

- 绑定一个 account id。
- 使用该 account 的 `app_id`、`app_secret`、`signing_secret`。
- 拥有独立 `SeaTalkOpenAPIClient`。
- 拥有独立 `SeaTalkEventDispatcher`。
- relay mode 下拥有独立 `SeaTalkRelayClient`。
- webhook mode 下通过 shared webhook server 路由到该 runtime。

优点：

- Hermes 只看到一个 `seatalk` platform，符合 Phase 1 plugin 边界。
- 不需要修改 hermes-agent core。
- 与 OpenClaw 的 account 语义一致，但保持 Hermes 的 platform 抽象稳定。
- account 复杂度封装在 plugin 内部，对用户暴露的接口较小。
- 可以同时支持 relay 和 webhook。

代价：

- `SeaTalkAdapter` 内部状态从单 client/dispatcher 变为 runtime map。
- webhook server 需要按 payload `app_id` 选择 signing secret 和 runtime。
- 出站 target 需要 account 选择规则。

### 3.2 方案 B：每个 account 注册一个动态 Hermes platform

示例：`seatalk.default`、`seatalk.staging`。

优点：

- Hermes status、home channel、授权配置表面上可以按 platform 分开。
- 出站 target 不需要额外 account prefix。

问题：

- 需要动态注册多个 platform entry，Hermes `Platform` enum/registry 对该模式未验证。
- 用户侧会看到多个 SeaTalk platform，概念上偏离“一个 SeaTalk plugin”。
- setup TUI、status、send_message、home channel 都会变复杂。
- 多帐号数量变成 platform 数量，插件内部边界泄漏到 Hermes core。

结论：拒绝。

### 3.3 方案 C：只支持多 relay 连接，不支持多 webhook

优点：

- 实施最快，relay client 天然按 app credentials 建立连接。
- 可以先满足当前 relay 部署场景。

问题：

- 与 OpenClaw 的 dual gateway mode 不一致。
- 配置允许 `mode=webhook` 但 runtime 不支持，会形成长期技术债。
- 未来补 webhook 时还要重新设计入站路由。

结论：不作为 Phase 2 总体方案。实施切片可以先落 relay，但最终设计必须覆盖 webhook。

## 4. 选择理由

方案 A 是唯一同时满足以下条件的方案：

- 不修改 hermes-agent core。
- 不扩散多个 Hermes platform。
- 保持 OpenClaw accounts 语义。
- 支持 relay 和 webhook 两种 gateway mode。
- 让 account 选择、鉴权、credentials、runtime 状态都收敛在 plugin 内部。

## 5. 后续影响

采用方案 A 后，Phase 2 实施必须包含：

- account config parser 和 account merge。
- `SeaTalkAdapter` runtime map。
- relay account 到 runtime 的直接 dispatch。
- webhook app_id 到 runtime 的路由。
- outbound target account prefix。
- home channel account selection。
- per-account policy enforcement。

这些内容已在 Phase 2 TD 中展开。
