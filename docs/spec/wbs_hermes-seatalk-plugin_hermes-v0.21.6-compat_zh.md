---
标题: Hermes SeaTalk Plugin 对 hermes-agent v0.21.6 的兼容性修复工作分解结构
状态: draft
更新日期: 2026-10-09
基线:
  hermes-agent 版本: v0.21.6 (release commit 818c13be1d)
参考材料:
  - target 解析 (tools/send_message_targets.py `resolve_send_target`; gateway/platform_registry.py `PlatformEntry.parse_target_ref_fn`)
  - 原始配置读取 (hermes_cli/config.py `read_raw_config`)
  - clarify 投递与收尾契约 (gateway/platforms/base.py `send_clarify`; gateway/run_turn_runner_clarify_delivery.py)
  - 插件清单版本门槛 (hermes_cli/plugins_loader.py `requires_hermes`)
文档摘要: 将 hermes-seatalk 插件适配 hermes-agent v0.21.6 所需的修复与验证拆解为任务和完成条件。
---

# Hermes SeaTalk Plugin 对 hermes-agent v0.21.6 的兼容性修复工作分解结构

## 1. 范围

插件此前基线为 v2026.7.30（v0.19.1）。对照 v0.21.6：

- 阻断项：
  - `tools.send_message_tool._parse_target_ref` 已移到 `tools/send_message_targets.py`，`register()` 里对它的 monkey-patch 抛 `AttributeError`，插件不加载。上游同时提供了 `PlatformEntry.parse_target_ref_fn`，`resolve_send_target` 先调用它。
  - PyYAML 不再随 Hermes 安装。`_raw_config_file` 读不到 `config.yaml`，返回 `{}`：带账号前缀的目标（`staging:EmpABC`）被拆成 chat `staging`、线程 `EmpABC`，设置向导重写 `config.yaml` 时只剩 seatalk 一节。
- 契约变化：clarify 的投递预算和文本兜底改由网关负责。网关等待 `send_clarify` 15 秒；返回失败时改发基类编号文本；超时或 `raw_response["ambiguous"]` 视为可能已送达，不重发。clarify 未经点击结束时（超时、`/new`、打字作答、无关文字取消），网关调用适配器的 `retire_clarify_card(clarify_id, notice)`。
- 测试漂移：测试直接访问已移走的私有名（`_parse_target_ref`、`cron.scheduler` 下的投递表），授权测试的假 runner 缺少 authz 新增的方法，`conftest.py` 的快照因前者失败而跳过了 `_send_to_platform`。

维持不变（已核对）：`_patch_send_to_platform`（插件平台走上游的适配器媒体路径时，只有媒体、没有文字的消息会被拒绝，视频和语音还要求适配器实现 `send_video`、`send_voice`）、`standalone_sender_fn`、`env_enablement_fn`、`cron_deliver_env_var`、插件重写的 `BasePlatformAdapter` 方法签名。

## 2. 任务清单

| ID | 任务 | 依赖 | 执行方式 | 覆盖范围 | 验收要点 |
| --- | --- | --- | --- | --- | --- |
| WC2-00 | target 解析改用 `parse_target_ref_fn` | 无 | AFK | `register(ctx)`、`_parse_seatalk_target_ref` | 插件加载；全部 target 格式经 `resolve_send_target` 解析正确 |
| WC2-01 | 原始配置改用 `read_raw_config` | 无 | AFK | `_raw_config_file` | 带账号前缀的目标解析正确；设置向导保留 `config.yaml` 其余内容 |
| WC2-02 | 声明版本门槛 | 无 | AFK | `plugin.yaml` | `requires_hermes: ">=0.21.6"` |
| WC2-03 | clarify 对齐网关契约 | 无 | AFK | `send_clarify`、`retire_clarify_card`、`README.md` | 卡片失败返回失败，由网关回落文本；未经点击结束的卡片被收尾 |
| WC2-04 | 测试对齐 | WC2-00 到 WC2-03 | AFK | `tests/` | 对 v0.21.6 全量通过；无 Hermes 时 stub 路径通过 |
| WC2-05 | VM 升级与端到端验证 | WC2-00 到 WC2-04 | HITL | 测试 VM 上的 Hermes 升级、插件部署、E2E | gateway 中 SeaTalk 处于 connected；文本收发、clarify 卡片点击与打字作答后的收尾正常 |

## 3. 任务明细

### WC2-00 target 解析改用 `parse_target_ref_fn`

- 删除 `_patch_send_message_tool` 及其调用；原解析逻辑改为 `_parse_seatalk_target_ref(target_ref) -> (chat_id, thread_id) | None`，作为 `parse_target_ref_fn` 注册。
- 解析失败返回 `None`。注册了解析函数的插件平台由上游按严格模式处理，无法解析的目标报错，不原样透传。

### WC2-01 原始配置改用 `read_raw_config`

- `_raw_config_file` 返回 `hermes_cli.config.read_raw_config()`：不合并默认值、不迁移，文件缺失或无法解析时为 `{}`。

### WC2-02 声明版本门槛

- 加载器在导入前检查 `requires_hermes`，低于门槛时跳过插件并记日志。

### WC2-03 clarify 对齐网关契约

- `send_clarify` 不再自设 deadline，也不自己回落文本。卡片发送抛错时返回 `success=False`，与内置平台一样不报告 `ambiguous`：发送超过 15 秒时由网关视为可能已送达。多选、开放式、选项超限或问题超长仍直接走基类文本。
- 发卡后不再调用 `mark_awaiting_text`。网关已原生处理卡片待答时的打字：数字或选项原文作为答案，其他文字取消该 clarify、收尾卡片并按普通消息处理；只有点 Other 后任意文字才作为答案。
- 卡片发送成功后按 `clarify_id` 记下卡片（`message_id`、会话、线程、账号），表有上限。点击处理完成时删除记录。
- `retire_clarify_card` 取出记录，以 `notice` 为状态行收尾卡片，没有记录时不做任何事。卡片发送返回前就结束的 clarify（与 Slack 一致），以及进程重启前发出的卡片（记录只在进程内存中），都不会被收尾，有人点击时显示已关闭。

### WC2-04 测试对齐

- 注册用例检查 `register()` 传入 `parse_target_ref_fn`；target 解析用例使用 `register()` 实际注册的条目，经 `resolve_send_target` 验证，带账号前缀的用例读取临时目录中真实的 `config.yaml`；cron 用例改用 `cron.scheduler_delivery`，只比对 `platform`、`chat_id`、`thread_id`。
- 授权用例的 runner 改为不经 `__init__` 构造的 `GatewayRunner`，只替换依赖运行中网关的方法，其余授权逻辑用真实实现。
- `conftest.py` 只快照插件实际改写的 `_send_to_platform`。
- clarify 用例改为验证发送失败时返回失败、不自行回落文本；新增收尾卡片的用例。

验证方式：

- 以 v0.21.6 为 Hermes 运行 pytest 全量通过；不安装 Hermes 时 stub 路径通过。
- 经真实插件加载器注册：平台、`seatalk` 工具、`parse_target_ref_fn` 与 `_send_to_platform` patch 均生效；`hermes plugins doctor seatalk-platform --ci` 通过。

### WC2-05 VM 升级与端到端验证

- 测试 VM 升级到 v0.21.6 后安装本版本插件，重启 gateway。
- 按 `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` 的 E-02、E-04 核对 SeaTalk 文本收发。
- clarify 卡片：点击选项、点 Other 后打字、直接打字作答三种情况下卡片都被收尾。
- `hermes plugins doctor seatalk-platform --ci` 通过。
