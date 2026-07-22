---
标题: Hermes SeaTalk Plugin 对 hermes-agent v2026.7.20 的兼容性修复工作分解结构
状态: draft
更新日期: 2026-07-22
基线:
  hermes-agent 版本: v2026.7.20 (Hermes Agent v0.19.0, release commit 3ef6bbd20)
参考材料:
  - hermes-agent v2026.7.20 平台适配器连接契约 (gateway/platforms/base.py `connect(self, *, is_reconnect: bool = False)`; gateway/run.py `_connect_adapter_with_timeout` 恒定传入 `is_reconnect=`)
  - hermes-agent 授权重构 (gateway/authz_mixin.py, `_is_user_authorized` 依赖 `_adapter_authorization_is_upstream` 与 `SessionSource.delivered_via_upstream_relay`)
  - hermes-agent 插件出站官方钩子 (gateway/platform_registry.py `PlatformEntry.standalone_sender_fn`; tools/send_message_tool.py `_send_via_adapter`)
  - hermes-agent vision 凭据修复 (commit 25aa626cb, 自 v2026.7.7 起随 release 发布, 取代本仓库 deploy/patches/hotfix-vision-runtime-credentials)
  - Hermes SeaTalk Plugin E2E 手册 (../test/e2e_hermes-seatalk-plugin_runbook_zh.md)
文档摘要: 将 hermes-seatalk 插件适配 hermes-agent v2026.7.20 所需的修复、清理与验证拆解为可执行任务、依赖关系、完成条件和验证方式。
---

# Hermes SeaTalk Plugin 对 hermes-agent v2026.7.20 的兼容性修复工作分解结构

## 1. 范围

本 WBS 针对 hermes-agent 官方 release **v2026.7.20**(release commit `3ef6bbd20`)
的兼容性修复。插件此前基线为「registry 钩子时代、`is_reconnect` 契约之前」的
hermes-agent main;对照 v2026.7.20 的分析结论:

- 阻断项:gateway 平台适配器连接契约新增 keyword-only 参数
  `is_reconnect`,gateway 首连与重连都会强制传入;插件 `SeaTalkAdapter.connect()`
  仍是旧签名,在 v2026.7.20 上每次连接抛 `TypeError`,SeaTalk 无法上线。
- 测试漂移:上游把授权逻辑重构进 `gateway/authz_mixin.py`,
  `_is_user_authorized` 调用 `self._adapter_authorization_is_upstream(...)`;
  插件授权测试的 `SimpleNamespace` 假 runner 缺少该方法,3 个用例失败
  (运行时不受影响)。
- 机制演化:上游为插件平台提供了官方出站钩子
  `PlatformEntry.standalone_sender_fn`(gateway 不在本进程时的一次性投递路径)。
  插件的 `_send_to_platform` monkey-patch 仍需保留——上游通用路径的
  live-adapter 分支只发文本(媒体被丢弃并附 warning),且不带
  `_skip_coalescing`;但无 runner 场景应迁移到官方钩子,使进程外
  cron 投递真正可用。
- 清理项:`deploy/patches/hotfix-vision-runtime-credentials` 修复的问题已由
  上游 commit `25aa626cb` 解决并自 v2026.7.7 起发布,按补丁自身 README 的
  删除条件应移除。

维持不变(已核对,无需改动):`plugin.yaml` 与 `register(ctx)` 装载契约、
`env_enablement_fn` home channel 钩子、`cron_deliver_env_var` 钩子、
`_parse_target_ref` patch(上游仍无第三方平台 target 解析钩子)。

任务 ID 使用 `WC-xx`(Compat),避免与 Phase 1 的 `W-xx`、Phase 2 的
`W2-xx` 混淆。

## 2. 任务清单

| ID | 任务 | 依赖 | 执行方式 | 覆盖范围 | 验收要点 |
| --- | --- | --- | --- | --- | --- |
| WC-00 | connect 签名对齐重连契约 | 无 | AFK | `SeaTalkAdapter.connect` | 接受 `is_reconnect` keyword;gateway 首连/重连调用不再抛 `TypeError` |
| WC-01 | 授权测试替身对齐 authz_mixin | 无 | AFK | `tests/test_w07_authorization.py` | t07_01/02/03 恢复通过;断言语义不变 |
| WC-02 | 出站 standalone_sender_fn 注册与无 runner 回退 | 无 | AFK | `register(ctx)`、`_seatalk_send_to_platform`、一次性投递路径 | 注册官方钩子;无 runner 时一次性投递;in-process 媒体/skip-coalescing 行为不回退 |
| WC-03 | 移除 vision hotfix 补丁目录 | 无 | AFK | `deploy/patches/hotfix-vision-runtime-credentials/` | 目录删除;删除依据可追溯(上游 25aa626cb ≥ v2026.7.7) |
| WC-04 | 本地回归收敛 | WC-00, WC-01, WC-02 | AFK | 全量 pytest 对 v2026.7.20 checkout | 0 失败;新增行为有测试覆盖 |
| WC-05 | VM 升级与端到端验证 | WC-00 到 WC-04 | HITL | 测试 VM hermes-agent 升级、skillhub 补丁重打、插件部署、hotfix 残留清理、E2E | VM hermes ≥ v2026.7.20;SeaTalk 收发与图片解析正常;skillhub 限源仍生效 |

## 3. 依赖关系

```text
WC-00 ─┐
WC-01 ─┼─> WC-04 ─> WC-05
WC-02 ─┘             ^
WC-03 ───────────────┘
```

## 4. 建议实施顺序

### Batch 1:代码修复与清理

包含:WC-00、WC-01、WC-02、WC-03

交付目标:

- 插件在 v2026.7.20 上可连接、可发送。
- 授权测试替身与上游 authz_mixin 对齐。
- 出站无 runner 场景走官方 standalone 钩子。
- 已失效的 vision hotfix 从仓库移除。

### Batch 2:本地回归

包含:WC-04

交付目标:

- 全量测试对 v2026.7.20 checkout 通过,形成 TR 依据。

### Batch 3:VM 部署与端到端验证

包含:WC-05

交付目标:

- 测试 VM 上 hermes-agent 升级至 v2026.7.20 并恢复受控 skillhub 限源。
- SeaTalk 插件新版本部署、gateway 重启、真实收发验证。

## 5. 任务明细

### WC-00 connect 签名对齐重连契约

目标:使 `SeaTalkAdapter.connect` 满足 v2026.7.20 gateway 的连接调用契约。

交付物:

- `SeaTalkAdapter.connect(self, *, is_reconnect: bool = False) -> bool`。

完成条件:

- `adapter.connect(is_reconnect=True)` 与 `adapter.connect()` 均可调用,
  返回语义与现状一致(无账号时告警并标记 running;有账号时按 runtime
  聚合结果返回)。
- `is_reconnect` 仅作契约兼容,不改变连接行为(与多数上游内置适配器
  的 accept-and-ignore 处理一致)。

验证方式:

- 新增契约测试:以 `is_reconnect=True/False` 两种方式调用 connect。

### WC-01 授权测试替身对齐 authz_mixin

目标:恢复 `GatewayRunner._is_user_authorized` 相关用例在 v2026.7.20 下通过。

交付物:

- `tests/test_w07_authorization.py` 的假 runner 增加
  `_adapter_authorization_is_upstream=lambda platform, *, profile=None: False`。

完成条件:

- t07_01(email 优先)、t07_02(employee code 回退)、t07_03(未授权拒绝)
  恢复通过。
- 断言语义不变:仍验证 env allowlist 匹配逻辑,不放宽授权路径。
- 真实 `SessionSource` 的 `delivered_via_upstream_relay` 默认 False,
  不需要在测试中显式伪造。

验证方式:

- `pytest tests/test_w07_authorization.py` 全绿。

### WC-02 出站 standalone_sender_fn 注册与无 runner 回退

目标:采用 v2026.7.20 官方 `PlatformEntry.standalone_sender_fn` 钩子,
使 gateway 不在本进程时(如独立进程运行的 cron 投递)SeaTalk 仍可送达;
同时保留 in-process monkey-patch 的媒体与 skip-coalescing 行为。

设计约束(为什么不是整体替换 monkey-patch):

- 上游 `_send_via_adapter` 的 live-adapter 分支只调用 `adapter.send()`
  发文本,`media_files` 不投递(仅附「media omitted」warning),
  也不带 `_skip_coalescing` 元数据;整体切换会回退进程内媒体发送。
- 上游通用路径按 chunk 循环调用且每个 chunk 都携带 `media_files`,
  多 chunk 时媒体会重复投递;插件自己的入口按「整条消息一次」处理更正确。

交付物:

- `_seatalk_standalone_send(pconfig, chat_id, message, *, thread_id=None,
  media_files=None, force_document=False)`:从 `pconfig` 构造一次性
  `SeaTalkAdapter`(OpenAPI client 惰性取 token,无需 connect),完成文本
  分块与媒体投递后关闭 client。
- `register(ctx)` 增加 `standalone_sender_fn=_seatalk_standalone_send`。
- `_seatalk_send_to_platform` 增加可选 `pconfig` 透传;runner/adapter
  查找(含既有重试退避)失败且拿到 `pconfig` 时回退到 standalone 路径。
- `_patch_send_to_platform` 保持,并把 `pconfig` 传入 SeaTalk 分支。

完成条件:

- 注册后 `PlatformEntry.standalone_sender_fn` 指向 standalone 实现。
- 无 runner 时:文本按 `max_message_length` 分块发送、图片走
  `send_image_file`、`force_document=True` 时图片改走 `send_document`、
  发送结果 dict 契约(`success`/`message_id`/`error`)与上游
  `_send_via_adapter` 校验一致。
- standalone 路径对邮箱 target 可解析(一次性 runtime 标记为可用后走
  既有 email→employee_code 解析);发送完成后 client 全部关闭。
- 有 runner 时行为不变:媒体经 live adapter 投递、`_skip_coalescing`
  元数据保留、gateway loop 编组不回退(t08 全部既有用例保持通过)。

验证方式:

- 新增 standalone 发送测试(注入 fake client,覆盖文本分块、图片/文档
  路由、force_document、client 关闭、错误传播)。
- 新增注册断言:`register(ctx)` 捕获 kwargs 中含 `standalone_sender_fn`。
- 既有 `tests/test_w08_runtime_patch.py` 全绿。

### WC-03 移除 vision hotfix 补丁目录

目标:清理已被上游取代的临时补丁,避免误用。

交付物:

- 删除 `deploy/patches/hotfix-vision-runtime-credentials/` 目录。

完成条件:

- 目录及其 README/apply.py/fix.diff/install.sh 全部移除。
- 删除依据:上游 commit `25aa626cb` 已包含同问题的更完整修复
  (桥接 runtime 凭据 + `_resolve_custom_runtime()` 兜底 + 测试),
  自 v2026.7.7 起随 release 发布;本补丁 README 的删除条件已满足。
- VM 侧备份文件清理归入 WC-05。

验证方式:

- 仓库树检查;`git status` 显示目录删除。

### WC-04 本地回归收敛

目标:在 hermes-agent v2026.7.20 checkout 上全量回归通过。

交付物:

- 全量 pytest 运行记录(0 失败)。

完成条件:

- `tests/` 全部用例(含 WC-00/WC-02 新增用例与 WC-01 修复用例)通过。
- 测试环境指向 v2026.7.20 checkout(`analysis/v2026.7.20` 分支),
  不向 hermes-agent 树写入任何文件。

验证方式:

- 全量 pytest,记录通过/失败计数。

### WC-05 VM 升级与端到端验证

目标:测试 VM 升级到 v2026.7.20 并验证插件端到端可用。

交付物:

- VM 上 hermes-agent 升级至 v2026.7.20。
- garena-skillhub 限源补丁在升级后重新应用(升级会覆盖
  `tools/skills_hub.py`)。
- SeaTalk 插件新版本部署与 gateway 重启。
- VM 上 vision hotfix 备份文件
  (`agent/auxiliary_client.py.bak.hotfix-vision-runtime-credentials`)清理。

完成条件:

- VM 上 hermes-agent 版本 ≥ v2026.7.20,gateway 正常启动,SeaTalk
  adapter 处于 connected。
- 升级后 `create_source_router()` 仅返回 `garena-skillhub`
  (skillhub 补丁验证脚本输出符合预期)。
- E2E:SeaTalk 端文本收发正常;发送图片可正常解析(确认 vision
  修复在上游版本中生效,hotfix 移除无回归)。
- 失败时保留现场并回报,不带病收尾。

验证方式:

- 按 `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` 手工核对
  关键路径;`hermes gateway status` 与 gateway 日志佐证。

## 6. 覆盖关系

| 分析结论 / 上游变化 | 覆盖任务 |
| --- | --- |
| `connect(is_reconnect=)` 连接契约(阻断项) | WC-00 |
| `authz_mixin` 重构引发的测试替身漂移 | WC-01 |
| `standalone_sender_fn` 官方出站钩子 | WC-02 |
| in-process 媒体 / skip-coalescing 行为保持 | WC-02 |
| 上游 vision 凭据修复取代本地 hotfix | WC-03, WC-05 |
| 升级覆盖 `tools/skills_hub.py` 需重打限源补丁 | WC-05 |
| v2026.7.20 全量回归与真实环境验证 | WC-04, WC-05 |
