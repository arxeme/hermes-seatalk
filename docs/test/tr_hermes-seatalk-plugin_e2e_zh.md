---
标题: Hermes SeaTalk Plugin 真实联调测试报告
状态: draft
更新日期: 2026-05-05
参考材料:
  - Hermes SeaTalk Plugin 测试计划 (./tp_hermes-seatalk-plugin_zh.md)
  - Hermes SeaTalk Plugin 测试报告 (./tr_hermes-seatalk-plugin_zh.md)
  - Hermes SeaTalk Plugin 真实联调 Runbook (./e2e_hermes-seatalk-plugin_runbook_zh.md)
文档摘要: 记录真实 SeaTalk 联调的执行结果、证据摘要、失败项和阻塞项。
---

# TR: Hermes SeaTalk Plugin 真实联调测试报告

## 1. 当前结论

真实 SeaTalk E2E 尚未执行。当前状态是自动化准备项已完成，人工环境准备与 E2E 用例均待执行。

本报告只记录结果，不重复执行步骤。具体操作步骤见 `e2e_hermes-seatalk-plugin_runbook_zh.md`。

## 2. 总体状态

| 类别 | 数量 | 结果 |
| --- | ---: | --- |
| 自动化准备项 | 6 | PASS |
| 人工环境准备项 | 9 | PENDING |
| 真实 E2E 用例 | 9 | PENDING |
| FAIL 项 | 0 | 无 |
| BLOCKED 项 | 0 | 无 |

## 3. 测试环境摘要

| 项目 | 当前记录 | 结果 | 备注 |
| --- | --- | --- | --- |
| Hermes 版本 | PENDING | PENDING | 需在目标联调机器确认 |
| Plugin 安装路径 | PENDING | PENDING | 预期为 `~/.hermes/plugins/seatalk` 或等价 user plugin 目录 |
| Plugin enable | PENDING | PENDING | 预期执行 `hermes plugins enable seatalk-platform` |
| 入站模式 | PENDING | PENDING | `relay` 或 `webhook` 至少一种 |
| SeaTalk Bot App | PENDING | PENDING | 需真实 App ID、App Secret、Signing Secret |
| 授权用户/群 | PENDING | PENDING | 需覆盖授权与未授权矩阵 |
| Home channel | PENDING | PENDING | 需覆盖默认发送目标 |

## 4. 自动化准备项结果

| 项目 | 结果 | 证据摘要 |
| --- | --- | --- |
| 本地 pytest 回归 | PASS | `83 passed`，见 `tr_hermes-seatalk-plugin_zh.md` |
| 覆盖率报告 | PASS | `TOTAL 76%`，见 `tr_hermes-seatalk-plugin_zh.md` |
| Plugin manifest/import | PASS | W-00 自动化测试覆盖 |
| relay/webhook 配置互斥 | PASS | W-01/W-09 自动化测试覆盖 |
| runtime patch 隔离 | PASS | W-08/W-10 自动化测试覆盖 |
| 文档与 runbook | PASS | W-09 自动化测试与本 runbook 覆盖 |

## 5. 人工准备项结果

| 项目 | 结果 | 证据摘要 | 问题链接 |
| --- | --- | --- | --- |
| 安装 plugin | PENDING | PENDING | PENDING |
| enable plugin | PENDING | PENDING | PENDING |
| setup TUI 可见 SeaTalk | PENDING | PENDING | PENDING |
| common credentials 配置 | PENDING | PENDING | PENDING |
| relay/webhook 模式配置 | PENDING | PENDING | PENDING |
| gateway restart | PENDING | PENDING | PENDING |
| gateway status | PENDING | PENDING | PENDING |
| 授权/未授权用户准备 | PENDING | PENDING | PENDING |
| 授权/未授权群准备 | PENDING | PENDING | PENDING |

## 6. 真实 E2E 结果

| 用例 | 验证目标 | 结果 | 证据摘要 | 问题链接 |
| --- | --- | --- | --- | --- |
| E-01 Bot App 配置 | credentials、plugin enable、TUI、status 链路可用 | PENDING | PENDING | PENDING |
| E-02 用户私聊入站 | 授权用户私聊进入 Hermes agent 并收到响应 | PENDING | PENDING | PENDING |
| E-03 群聊入站 | 授权群内授权用户消息进入正确 channel/thread | PENDING | PENDING | PENDING |
| E-04 出站工具调用 | `send_message(target="seatalk")` 到达 SeaTalk | PENDING | PENDING | PENDING |
| E-05 Home Channel | home channel 和 thread id 行为符合配置 | PENDING | PENDING | PENDING |
| E-06 未授权用户 | 非 allowlist 用户无法触发 agent | PENDING | PENDING | PENDING |
| E-07 未授权群 | 非 group allowlist 群被 dispatcher 预过滤 | PENDING | PENDING | PENDING |
| E-08 文件或图片 | 入站附件 metadata 与出站附件/降级行为符合预期 | PENDING | PENDING | PENDING |
| E-09 Runtime Health | relay/webhook 中断与恢复可观察，恢复后可继续收发 | PENDING | PENDING | PENDING |

## 7. FAIL / BLOCKED 分析

当前没有已执行失败项，也没有已确认阻塞项。

| 项目 | 状态 | 说明 | 处理方式 |
| --- | --- | --- | --- |
| 真实 SeaTalk credentials | PENDING | 尚未提供真实 Bot App credentials | 准备测试 Bot App 后执行 E-01 |
| 入站通道可达性 | PENDING | relay/webhook 尚未选择并验证 | 选择一种模式并按 runbook 执行 |
| 授权测试对象 | PENDING | 授权/未授权用户和群尚未确认 | 准备测试矩阵后执行 E-02/E-03/E-06/E-07 |
| 文件/图片素材 | PENDING | 附件权限与测试素材尚未确认 | 准备小图片、小文档后执行 E-08 |

## 8. 记录规范

- 不记录 `SEATALK_APP_SECRET`、`SEATALK_SIGNING_SECRET`、access token、私钥或完整 callback token。
- 用户 email、群名、群 id 可按内部安全要求脱敏；必须保留“授权/未授权”类别。
- 每个人工用例至少保留一条 Hermes 侧日志证据和一条 SeaTalk 侧现象证据。
- 自动化可覆盖的缺陷应补到 `tests/`；真实环境限定问题记录到本 TR 和独立 issue。
