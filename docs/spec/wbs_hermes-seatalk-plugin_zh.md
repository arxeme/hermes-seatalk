---
title: Hermes SeaTalk Plugin 工作分解结构
status: draft
updated: 2026-05-04
related_td: ./td_hermes-seatalk-plugin_zh.md
related_test_plan: ../test/tp_hermes-seatalk-plugin_zh.md
---

# Hermes SeaTalk Plugin 工作分解结构

## 1. 范围

本 WBS 基于 `td_hermes-seatalk-plugin_zh.md`，目标是在 Hermes 官方新版本上以外部 plugin 方式提供 SeaTalk 平台接入能力。实现边界如下：

- SeaTalk 相关代码位于 plugin 包内，Hermes 仓库不提交 SeaTalk 专属代码。
- Plugin 通过 `register(ctx)` 在 Hermes 进程启动时注册平台和兼容性补丁。
- 当前 TD 中需要 monkey patch 的部分视为 runtime compatibility patch，必须可重复调用且不可产生重复包装。
- 网关用户鉴权以 Hermes 当前支持的 email allowlist 为准；`employee_code` 只作为无 email 时的 fallback 标识。
- 群白名单只做 SeaTalk channel 预过滤，不替代 Hermes gateway 用户 allowlist。

当前没有单独 PRD，本 WBS 直接承接 TD 的技术方案、旧版 SeaTalk TD 的能力目标，以及本轮设计 review 已收敛的约束。

## 2. 任务清单

| ID | 任务 | 依赖 | 执行方式 | 覆盖范围 | 验收要点 |
| --- | --- | --- | --- | --- | --- |
| W-00 | Plugin 包骨架与安装入口 | 无 | AFK | plugin manifest、包结构、依赖声明、配置样例 | Hermes 能 discover 并 import plugin；未启用时无副作用 |
| W-01 | Plugin 注册与平台状态语义 | W-00 | AFK | `register(ctx)`、平台注册、配置校验、PlatformEntry 回调 | Hermes plugin enable 后注册 `seatalk`；`configured/enabled/connected` 语义与 TD 一致 |
| W-02 | SeaTalk OpenAPI 客户端 | W-00 | AFK | app token、用户解析、消息发送、native media payload、错误映射 | OpenAPI 调用可 mock 测试；错误不会泄漏敏感配置 |
| W-03 | Hermes 出站适配器 | W-01, W-02 | AFK | Hermes message 到 SeaTalk outbound payload 的转换 | 文本、文件、图片、分片、出站 coalescer 和失败重试策略符合 TD |
| W-04 | Webhook 入站模式 | W-01, W-02 | AFK | webhook route、签名校验、事件解析、响应控制 | SeaTalk webhook 能转成 Hermes 输入事件；非法请求被拒绝 |
| W-05 | Relay 入站模式 | W-01, W-02 | AFK | relay client、WebSocket 生命周期、重连、心跳 | relay 模式必须校验 `SEATALK_RELAY_URL`；断线可恢复 |
| W-06 | 入站标准化与调度 | W-04, W-05 | AFK | 去重、debounce、quoted message、附件下载、session 映射 | webhook/relay 进入同一 Hermes 执行链路 |
| W-07 | 鉴权与群过滤 | W-04, W-05, W-06 | AFK | `user_id/user_id_alt` 设置、群白名单、拒绝日志 | 未授权用户不会进入 agent；群过滤不误当用户授权 |
| W-08 | Hermes 兼容性补丁 | W-01, W-03, W-06 | AFK | `send_message`、`send_to_platform`、home channel、cron target | 补丁可重复注册；不会破坏内置平台；home channel 支持 thread id |
| W-09 | 配置、安装与运维文档 | W-01 到 W-08 | AFK | README、env 示例、setup wizard、运行说明、状态排查 | 使用者可按文档安装、启用、TUI 配置、重启并验证 plugin |
| W-10 | 自动化测试集 | W-01 到 W-08 | AFK | pytest 单测、集成测试、mock OpenAPI/relay/webhook | 核心路径在 CI 可离线验证 |
| W-11 | 真实 SeaTalk 联调验证 | W-09, W-10 | HITL | Bot App、真实用户、真实群、真实文件消息 | 完成端到端收发、鉴权拒绝、relay/webhook 至少一种生产路径验证 |

## 3. 依赖关系

```text
W-00
  -> W-01
      -> W-03 -> W-08
      -> W-04 -> W-06 -> W-07 -> W-10
      -> W-05 -> W-06
  -> W-02 -> W-03/W-04/W-05
W-09 depends on W-01..W-08
W-11 depends on W-09 and W-10
```

执行顺序应以依赖为准；如果实现中发现 TD 与 Hermes 实际 plugin API 不一致，应先更新 TD 或在 W-01 中记录差异，再继续后续任务。

## 4. 任务明细

### W-00 Plugin 包骨架与安装入口

目标：建立可被 Hermes 官方 plugin loader 识别的外部 plugin 包。

交付物：

- plugin repo 根目录下的 loader shim，例如 `adapter.py`、`__init__.py`。
- `hermes_seatalk/` Python package，例如 `adapter.py`、`client.py`、`dispatcher.py`。
- plugin manifest，例如 `plugin.yaml` 或 Hermes 当前 loader 要求的等价文件。
- `pyproject.toml` 或等价依赖声明。
- 最小导出入口：root `adapter.py` re-export `hermes_seatalk.adapter.register(ctx)`。
- `env.example`，只包含 SeaTalk plugin 必需配置。

完成条件：

- plugin 未 enable 时，Hermes 启动不会 import 或执行 SeaTalk 运行时代码。
- plugin enable 后，Hermes discover 过程中可以找到包和 manifest。
- import 失败时错误信息能定位到缺失依赖或配置问题。
- 不需要修改 Hermes 官方仓库文件即可完成安装。

验证方式：

- 本地最小 Hermes 启动 smoke test。
- manifest schema 单测。
- `register(ctx)` import 单测。

### W-01 Plugin 注册与平台状态语义

目标：将 SeaTalk 注册为 Hermes 平台，并定义一致的配置、启用和连接状态。

交付物：

- `register(ctx)` 中的平台注册逻辑。
- `check_seatalk_requirements()`。
- `validate_config()`、`check_fn`、`is_connected` 三个 PlatformEntry 回调的实现与注册。
- 文档化 Hermes gateway 如何调用这些回调展示平台状态和决定 adapter 启动。

完成条件：

- plugin 被 `hermes plugins enable seatalk-platform` 启用，且必需配置完整时，平台状态为 configured/enabled。
- `SEATALK_MODE` 必须显式校验为 `relay` 或 `webhook`。
- relay 模式下必须检查 `SEATALK_RELAY_URL`。
- webhook 模式下必须检查 webhook 所需 secret 或签名配置。
- 缺少 app id、app secret、signing secret、mode 等关键配置时给出明确失败原因。
- `_is_seatalk_connected` 与 `_validate_seatalk_config` 返回值一致：credentials 完整即视为 connected，用于 Hermes gateway 创建 adapter。
- relay/webhook 的真实运行时健康由 health state 文件或 adapter 内部状态表达，不通过 `is_connected` 返回值表达。
- 多次调用 `register(ctx)` 不重复注册平台或重复包裹函数。

验证方式：

- 环境变量矩阵单测。
- 重复 register 幂等性单测。
- 健康状态文件读取与缺失场景单测。

### W-02 SeaTalk OpenAPI 客户端

目标：封装 SeaTalk OpenAPI，向上提供稳定、可测试的客户端接口。

交付物：

- access token 获取和缓存。
- user id、email、employee code 的解析接口。
- 文本、图片、文件等消息发送接口。
- native image/file payload 构造或媒体资源处理接口。
- 统一异常类型和错误码映射。
- 请求日志脱敏策略。

完成条件：

- token 过期后可刷新，刷新失败不污染旧 token 状态。
- 发送失败能区分限流、鉴权失败、目标不存在、网络错误和协议错误。
- 所有日志中 app secret、access token、签名 secret 被脱敏。
- 对 SeaTalk API 的超时、重试和 backoff 有明确默认值和可配置项。

验证方式：

- `aiohttp` mock server 单测。
- token 缓存和刷新测试。
- 错误码映射测试。
- 日志脱敏测试。

### W-03 Hermes 出站适配器

目标：将 Hermes 内部消息转换为 SeaTalk 可发送的消息。

交付物：

- `SeaTalkAdapter.send(chat_id, content, metadata=None)`。
- `send_image_file()`、`send_document()` 等 native media 发送方法。
- `hermes_seatalk/coalescer.py` 出站文本合并器。
- Hermes target 到 SeaTalk 目标的解析。
- 文本分段、native image/file payload、图片/文件消息转换。
- 发送失败时的异常和 retry policy。

完成条件：

- `target="seatalk"` 可以通过 W-08 的工具补丁进入 SeaTalk 出站适配器。
- 支持向 home channel、指定 channel、指定 thread 或指定用户发送。
- 长文本按 SeaTalk 限制分段，分段顺序稳定。
- 出站 coalescer 默认开启，按 `(chat_id, thread_id)` 隔离；关闭开关生效；adapter shutdown 时 flush。
- media 不进入 coalescer。
- 文件和图片消息不因 MIME 或文件名缺失导致崩溃。
- 出站失败能回传给 Hermes 调用方，而不是静默吞掉。

验证方式：

- outbound payload snapshot 测试。
- 长文本分段测试。
- outbound coalescer 测试。
- native media payload mock 测试。
- 发送失败传播测试。

### W-04 Webhook 入站模式

目标：支持 SeaTalk webhook 事件进入 Hermes。

交付物：

- webhook HTTP handler。
- 签名校验。
- `event_verification` challenge 响应。
- SeaTalk 事件解析器。
- webhook ack 与异步处理分离策略。

完成条件：

- 合法 SeaTalk message event 能生成 Hermes 标准输入。
- `event_type=event_verification` 且签名有效时返回 `seatalk_challenge`。
- 签名无效或 payload malformed 时拒绝处理。
- webhook ack 不等待长时间 agent 执行。
- webhook 处理路径能更新运行时健康状态。

验证方式：

- HTTP handler 集成测试。
- 签名正反例测试。
- malformed payload 测试。
- ack 延迟测试。

### W-05 Relay 入站模式

目标：支持通过 seatalk-relay 或兼容服务接入 SeaTalk 事件。

交付物：

- relay WebSocket client。
- reconnect、heartbeat、backoff。
- relay 消息协议解析。
- relay 健康状态更新。

完成条件：

- relay 模式缺少 `SEATALK_RELAY_URL` 时平台不可配置。
- relay 连接建立、断开、重连均可观察。
- relay 收到的事件与 webhook 事件进入同一标准化路径。
- relay 连接失败不阻塞 Hermes 主进程退出。

验证方式：

- mock WebSocket server 集成测试。
- 重连和 backoff 测试。
- relay 协议 malformed 测试。
- 进程 shutdown 测试。

### W-06 入站标准化与调度

目标：将 SeaTalk 入站事件转换为 Hermes 可以执行的会话输入。

交付物：

- SeaTalk inbound event normalizer。
- session key 生成规则。
- 去重缓存。
- debounce 逻辑。
- quoted message 和附件下载处理。
- Hermes gateway/agent 调度入口封装。

完成条件：

- webhook 与 relay 共享同一标准化逻辑。
- 同一 SeaTalk 事件重复投递不会重复触发 agent。
- 连续短消息可按 TD debounce 规则合并后调度。
- quoted message、thread id、channel id 能保留到上下文 metadata。
- 附件下载失败不会导致整条用户文本丢失。

验证方式：

- normalizer 单测。
- duplicate event 测试。
- debounce 时间控制测试。
- quoted message 和附件路径测试。

### W-07 鉴权与群过滤

目标：保持 Hermes gateway 鉴权边界清晰，同时提供 SeaTalk 群过滤能力。

交付物：

- 使用 W-02/W-06 已解析出的 email 和 employee code 设置 Hermes `MessageEvent.user_id` / `user_id_alt`。
- group/channel allowlist 预过滤。
- email allowlist 对接 Hermes gateway 现有鉴权路径。
- 授权拒绝日志。

完成条件：

- 有 email 时优先使用 email 进入 Hermes gateway 用户鉴权。
- 无 email 时才使用 `employee_code` fallback；fallback 不应被描述为可绕过 Hermes allowlist。
- 群白名单只拒绝不在范围内的 channel，不把群授权等同于用户授权。
- 未授权事件不会进入 agent 执行。
- 拒绝日志包含 channel、user 标识和原因，但不包含敏感 token。

验证方式：

- email 优先级测试。
- employee fallback 测试。
- group pre-filter 测试。
- 未授权不调度测试。

### W-08 Hermes 兼容性补丁

目标：在不修改 Hermes 仓库源码的前提下，让现有 Hermes 工具链识别 SeaTalk target 和 home channel。

交付物：

- `_patch_send_message_tool()`。
- `_patch_send_to_platform()`。
- `_patch_home_channel()`。
- `_patch_cron_scheduler()`。
- 补丁幂等性 guard。

完成条件：

- `send_message(target="seatalk")` 可发送 SeaTalk 消息。
- `send_to_platform("seatalk", ...)` 可路由到 SeaTalk 平台。
- `get_home_channel("seatalk")` 返回 channel id，并支持 `SEATALK_HOME_CHANNEL_THREAD_ID`。
- cron target 设为 SeaTalk 时能使用 home channel。
- 多次 register 不导致函数被多层包装。
- Slack、Discord 等内置平台行为保持原样。

验证方式：

- monkey patch 幂等性测试。
- `send_message` parser 测试。
- home channel thread id 测试。
- 内置平台回归测试。

### W-09 配置、安装与运维文档

目标：让使用者可以独立安装、启用、运行和排查 SeaTalk plugin。

交付物：

- README。
- `env.example`。
- 安装说明。
- Hermes gateway setup / TUI 引导说明。
- Hermes enable/restart 说明。
- webhook/relay 二选一配置说明。
- 状态排查说明。

完成条件：

- 文档明确 plugin enable 只是写入 Hermes 配置，实际 `register(ctx)` 在 Hermes 进程启动或 plugin discovery 时运行。
- 文档明确用户安装的 plugin 需要先 `hermes plugins enable seatalk-platform`，之后才会出现在 `hermes setup` / `hermes gateway setup` 的 messaging platform TUI 中。
- setup wizard 先询问通用 credentials，再选择 `relay` 或 `webhook`。
- setup wizard 只询问并校验当前 mode 对应的额外字段；relay 只要求 `SEATALK_RELAY_URL`，webhook 不要求 relay URL。
- 文档明确修改配置后需要重启相关 Hermes 进程。
- 文档说明 relay 模式和 webhook 模式的配置差异。
- 文档说明 email allowlist 与群白名单的不同边界。
- 文档包含最小可运行配置和常见错误排查。

验证方式：

- 文档命令 smoke test。
- env 示例字段完整性测试。
- 人工按 README 完成一次本地启用。

### W-10 自动化测试集

目标：建立能在 CI 中离线运行的测试覆盖，降低 plugin 与 Hermes 官方版本变更的回归风险。

交付物：

- pytest 单元测试。
- mock HTTP/WebSocket 集成测试。
- monkey patch 回归测试。
- 配置矩阵测试。
- CI 命令说明。

完成条件：

- 不依赖真实 SeaTalk 凭证即可运行核心测试。
- 关键路径测试覆盖出站、入站、鉴权、配置、runtime patch。
- 失败断言能指向具体模块和场景。
- 测试不会污染全局环境变量或 Hermes 单例状态。

验证方式：

- `uv run pytest` 或项目约定命令。
- 覆盖率报告。
- 重复运行一致性检查。

### W-11 真实 SeaTalk 联调验证

目标：用真实 SeaTalk Bot App 验证自动化测试无法覆盖的外部集成。

交付物：

- 联调记录。
- Bot App 配置截图或配置摘要。
- 真实消息收发验证记录。
- 未授权用户和未授权群拒绝记录。
- 真实文件或图片消息验证记录。

完成条件：

- 至少一种入站模式完成真实端到端验证。
- home channel 和 thread id 行为符合预期。
- 出站工具调用能到达真实 SeaTalk 会话。
- 未授权用户无法触发 agent。
- 真实环境问题被反馈到 TD/WBS/TP 或实现 issue。

验证方式：

- 人工联调。
- 日志审查。
- SeaTalk 客户端侧消息确认。

## 5. 覆盖关系

| 需求/能力 | 对应任务 |
| --- | --- |
| Plugin 外部安装与启用 | W-00, W-01, W-09 |
| 平台注册与状态展示 | W-01 |
| Hermes 出站发送到 SeaTalk | W-02, W-03, W-08 |
| SeaTalk 入站触发 Hermes agent | W-04, W-05, W-06 |
| relay 模式 | W-01, W-05, W-10, W-11 |
| webhook 模式 | W-01, W-04, W-10, W-11 |
| email allowlist 鉴权 | W-06, W-07 |
| 群白名单预过滤 | W-07 |
| home channel 与 thread id | W-08, W-11 |
| 出站 coalescer | W-03, W-10 |
| runtime compatibility patch | W-01, W-08, W-10 |
| 安装、配置、运维说明 | W-09 |
| 自动化回归保护 | W-10 |
| 真实外部系统验证 | W-11 |

## 6. 风险与处理

| 风险 | 影响 | 对应任务 | 处理方式 |
| --- | --- | --- | --- |
| Hermes plugin API 与 TD 描述不一致 | 注册或平台路由无法实现 | W-01, W-08 | 先用最小 smoke test 确认可用 API，再更新 TD 或实现 |
| runtime monkey patch 受 Hermes 内部重构影响 | 官方升级后出站或 home channel 失效 | W-08, W-10 | 为每个 patch 写回归测试，失败时明确指向变更点 |
| SeaTalk API 凭证和真实环境不可用于 CI | 自动化无法覆盖真实链路 | W-02, W-11 | CI 使用 mock server；真实链路作为 HITL 验证 |
| email 缺失导致 Hermes gateway 鉴权失败 | 用户无法触发 agent | W-07, W-11 | 明确 email 优先和 employee fallback 行为，联调中覆盖无 email 用户 |
| relay/webhook 双模式状态语义混淆 | status 显示误导运维 | W-01, W-04, W-05 | static configured 与 runtime connected 分开测试 |
| 全局环境变量和单例状态污染测试 | 测试不稳定 | W-10 | pytest fixture 隔离 env、registry 和 patch 状态 |
