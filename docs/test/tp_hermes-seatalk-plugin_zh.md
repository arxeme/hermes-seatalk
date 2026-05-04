---
title: Hermes SeaTalk Plugin 测试计划
status: draft
updated: 2026-05-04
related_td: ../spec/td_hermes-seatalk-plugin_zh.md
related_wbs: ../spec/wbs_hermes-seatalk-plugin_zh.md
---

# Hermes SeaTalk Plugin 测试计划

## 1. 测试目标

本测试计划覆盖 Hermes SeaTalk Plugin 的外部 plugin 安装、平台注册、SeaTalk 收发、鉴权、runtime compatibility patch 和真实联调。测试设计以离线自动化为主，真实 SeaTalk 环境验证作为人工联调补充。

测试边界：

- 自动化测试不依赖真实 SeaTalk 凭证。
- Hermes 官方仓库不引入 SeaTalk 专属源码修改。
- 与 Hermes 内部函数相关的 monkey patch 必须有回归测试。
- relay 和 webhook 可分别测试，但入站标准化和调度逻辑必须共享测试。
- 鉴权测试以 Hermes 当前 email allowlist 能力为准。

## 2. 测试环境

| 类型 | 工具/方式 | 用途 |
| --- | --- | --- |
| 单元测试 | `pytest` | 配置、client、normalizer、auth、patch guard |
| 异步测试 | `pytest-asyncio` | webhook handler、relay client、async OpenAPI |
| HTTP mock | `aiohttp` test server 或同等 fixture | SeaTalk OpenAPI mock、webhook request |
| WebSocket mock | `aiohttp` WebSocket server 或同等 fixture | relay 连接、断线、重连 |
| 环境隔离 | pytest fixture | env var、registry、patch 状态隔离 |
| 真实联调 | SeaTalk Bot App + Hermes 本地/测试环境 | 端到端验证 |

建议测试目录：

```text
tests/
  unit/
    test_config.py
    test_registration.py
    test_openapi_client.py
    test_outbound_adapter.py
    test_inbound_normalizer.py
    test_auth.py
    test_runtime_patches.py
  integration/
    test_webhook_mode.py
    test_relay_mode.py
    test_gateway_dispatch.py
  e2e/
    README.md
```

## 3. 自动化测试用例

### T-00 Plugin 包骨架与安装入口

覆盖 WBS：W-00

| 用例 | 断言 |
| --- | --- |
| T-00-01 manifest 可解析 | plugin manifest 字段完整，名称、入口、依赖声明符合 Hermes loader 要求 |
| T-00-02 未启用无副作用 | 未 enable 时不注册 SeaTalk 平台、不修改 Hermes 函数 |
| T-00-03 register 可 import | plugin root 的 `adapter.register` 可导入，缺依赖时错误可诊断 |
| T-00-04 env 示例完整 | `env.example` 覆盖 TD 中必需配置，未包含真实 secret |

### T-01 Plugin 注册与平台状态语义

覆盖 WBS：W-01

| 用例 | 断言 |
| --- | --- |
| T-01-01 最小配置通过 | plugin 已通过 `hermes plugins enable seatalk-platform` 启用，且必需配置完整时 configured/enabled 为 true |
| T-01-02 缺少 credentials 失败 | 缺少 app id、app secret 或 signing secret 时配置校验失败并返回明确原因 |
| T-01-03 relay URL 必填 | relay 模式缺少 `SEATALK_RELAY_URL` 时配置校验失败 |
| T-01-04 webhook secret 必填 | webhook 模式缺少签名配置时配置校验失败 |
| T-01-05 `is_connected` 与配置校验一致 | `_is_seatalk_connected(cfg)` 与 `_validate_seatalk_config(cfg)` 返回值一致 |
| T-01-06 runtime health 不影响 adapter 创建 | runtime health file 不存在时，只要 credentials 完整，`is_connected` 仍返回 true |
| T-01-07 invalid mode 拒绝 | `SEATALK_MODE` 不是 `relay` 或 `webhook` 时，`check_seatalk_requirements()` 和 `_validate_seatalk_config()` 均返回 false |
| T-01-08 register 幂等 | 连续调用 `register(ctx)` 不重复注册平台、不重复 patch |

### T-02 SeaTalk OpenAPI 客户端

覆盖 WBS：W-02

| 用例 | 断言 |
| --- | --- |
| T-02-01 token 获取成功 | mock OpenAPI 返回 token 后客户端缓存 token |
| T-02-02 token 过期刷新 | token 过期后刷新；刷新失败不污染仍可用的旧状态 |
| T-02-03 发送文本成功 | 文本 payload、target、headers 与 SeaTalk 协议约定一致 |
| T-02-04 native media payload | 图片和文件按 SeaTalk native payload 规则构造，base64 内容、文件名和消息类型正确 |
| T-02-05 错误码映射 | 限流、鉴权失败、目标不存在、网络错误映射到统一异常 |
| T-02-06 日志脱敏 | app secret、access token、签名 secret 不出现在日志中 |

### T-03 Hermes 出站适配器

覆盖 WBS：W-03

| 用例 | 断言 |
| --- | --- |
| T-03-01 home channel 发送 | 未指定目标时使用 `SEATALK_HOME_CHANNEL` |
| T-03-02 指定 channel 发送 | 指定 channel id 时 payload 目标正确 |
| T-03-03 指定 thread 发送 | 配置 thread id 时 payload 保留 thread 信息 |
| T-03-04 长文本分段 | 超过限制的文本按顺序分段发送 |
| T-03-05 图片和文件消息 | 图片、文件附件按 native media payload 生成正确消息 |
| T-03-06 发送失败传播 | OpenAPI 失败向 Hermes 调用方返回可诊断错误 |
| T-03-07 coalescer 默认合并 | `SEATALK_OUTBOUND_COALESCING` 默认开启，同一 `(chat_id, thread_id)` 的连续文本按窗口合并 |
| T-03-08 coalescer 隔离和关闭 | 不同 thread 不互相合并；`SEATALK_OUTBOUND_COALESCING=false` 时逐条发送 |
| T-03-09 coalescer shutdown flush | adapter shutdown 时 flush 未发送文本；media 不进入 coalescer |

### T-04 Webhook 入站模式

覆盖 WBS：W-04

| 用例 | 断言 |
| --- | --- |
| T-04-01 合法事件入站 | 合法 SeaTalk message event 转成 Hermes 输入事件 |
| T-04-02 签名无效拒绝 | 签名错误时不进入 normalizer 和 agent |
| T-04-03 event verification | `event_type=event_verification` 且签名有效时返回 `{"seatalk_challenge": "..."}` |
| T-04-04 malformed payload | payload 缺字段或格式错误时返回可诊断错误 |
| T-04-05 快速 ack | webhook ack 不等待 agent 长任务完成 |
| T-04-06 health 更新 | webhook 成功处理后更新 runtime health |
| T-04-07 event verification 签名无效 | `event_type=event_verification` 但签名错误时，不返回 challenge，返回拒绝响应 |

### T-05 Relay 入站模式

覆盖 WBS：W-05

| 用例 | 断言 |
| --- | --- |
| T-05-01 relay 连接成功 | WebSocket 建连后状态更新为 connected |
| T-05-02 relay 消息解析 | relay message event 进入同一 normalizer |
| T-05-03 relay malformed | 协议消息异常时记录错误但 client 不崩溃 |
| T-05-04 断线重连 | mock server 断开后按 backoff 重连 |
| T-05-05 heartbeat 超时 | heartbeat 超时后状态更新并触发重连 |
| T-05-06 shutdown | Hermes 停止时 relay client 能按时退出 |

### T-06 入站标准化与调度

覆盖 WBS：W-06

| 用例 | 断言 |
| --- | --- |
| T-06-01 webhook/relay 同构 | 两种来源的同类事件生成相同 Hermes input schema |
| T-06-02 session key 稳定 | 同一用户同一 channel/thread 生成稳定 session key |
| T-06-03 去重 | 相同 SeaTalk event id 重复投递只触发一次 agent |
| T-06-04 debounce 合并 | 连续短消息在窗口内合并，顺序不变 |
| T-06-05 quoted message | 引用消息保留到 metadata 或上下文文本 |
| T-06-06 附件失败降级 | 附件下载失败时文本仍可进入 agent，错误写入 metadata |

### T-07 鉴权与群过滤

覆盖 WBS：W-07

| 用例 | 断言 |
| --- | --- |
| T-07-01 email 优先 | SeaTalk 用户有 email 时使用 email 进入 Hermes gateway 鉴权 |
| T-07-02 employee fallback | 无 email 时才使用 employee code fallback，且行为与 TD 描述一致 |
| T-07-03 未授权用户拒绝 | 不在 allowlist 的用户不会触发 agent |
| T-07-04 群白名单通过 | channel 在 group allowlist 中时继续执行用户鉴权 |
| T-07-05 群白名单拒绝 | channel 不在 allowlist 中时直接拒绝且不查 agent |
| T-07-06 拒绝日志脱敏 | 拒绝日志包含原因，不包含 token 或 secret |

### T-08 Hermes 兼容性补丁

覆盖 WBS：W-08

| 用例 | 断言 |
| --- | --- |
| T-08-01 `send_message` 支持 SeaTalk | `target="seatalk"` 能路由到 SeaTalk adapter |
| T-08-02 `send_to_platform` 支持 SeaTalk | 平台名为 `seatalk` 时调用 SeaTalk 平台 entry |
| T-08-03 home channel | `get_home_channel("seatalk")` 返回 `SEATALK_HOME_CHANNEL` |
| T-08-04 home thread id | `SEATALK_HOME_CHANNEL_THREAD_ID` 存在时被保留 |
| T-08-05 cron target | cron 目标为 SeaTalk 时使用 SeaTalk home channel |
| T-08-06 patch 幂等 | 多次 register 后每个被 patch 函数只包装一次 |
| T-08-07 内置平台回归 | Slack、Discord 等已有平台 target 行为不变 |
| T-08-08 target parser 全格式 | `_parse_target_ref("seatalk", ...)` 对 employee code、email、group/id、email:thread、employee:thread、group/id:thread 全部返回正确的 `(chat_id, thread_id, True)` |

### T-09 配置、安装与运维文档

覆盖 WBS：W-09

| 用例 | 断言 |
| --- | --- |
| T-09-01 README 命令可执行 | README 中本地安装和启用命令在测试环境可运行 |
| T-09-02 enable/restart 说明准确 | 文档明确 enable 只写配置，register 在进程启动或 discovery 时执行 |
| T-09-03 双模式配置清晰 | relay 和 webhook 的必填环境变量不混淆 |
| T-09-04 鉴权边界清晰 | 文档区分 email allowlist、employee fallback 和群白名单 |
| T-09-05 排查路径可用 | status、日志、health 文件的排查说明能定位常见问题 |

### T-10 自动化测试集自身质量

覆盖 WBS：W-10

| 用例 | 断言 |
| --- | --- |
| T-10-01 测试可离线运行 | 不设置真实 SeaTalk secret 时核心测试仍可通过 |
| T-10-02 env 隔离 | 单个测试修改环境变量不会影响其他测试 |
| T-10-03 registry 隔离 | 平台 registry 在测试间可恢复 |
| T-10-04 patch 状态隔离 | monkey patch 测试不会污染后续用例 |
| T-10-05 重复运行稳定 | 连续运行测试结果一致 |

## 4. 真实 SeaTalk 联调用例

覆盖 WBS：W-11

| 用例 | 操作 | 通过标准 |
| --- | --- | --- |
| E-01 Bot App 配置 | 在 SeaTalk 创建或配置 Bot App，设置 webhook 或 relay 所需凭证 | Hermes status 显示 SeaTalk configured |
| E-02 用户私聊入站 | 授权用户向 bot 发送文本 | Hermes agent 收到输入并产生响应 |
| E-03 群聊入站 | 授权群内授权用户发送文本 | 消息进入正确 session，channel metadata 正确 |
| E-04 出站工具调用 | Hermes 调用 `send_message(target="seatalk")` | SeaTalk 客户端收到消息 |
| E-05 home channel | 触发 cron 或 home channel 发送 | 消息到达 `SEATALK_HOME_CHANNEL`，thread id 行为符合配置 |
| E-06 未授权用户 | 未授权用户发送消息 | agent 未执行，日志记录拒绝原因 |
| E-07 未授权群 | 非白名单群发送消息 | agent 未执行，日志记录 channel 拒绝原因 |
| E-08 文件或图片 | 发送或转发文件/图片 | Hermes 能处理 metadata，出站附件可发送或明确降级 |
| E-09 relay/webhook runtime health | 停止并恢复 relay 或 webhook 可达性 | 状态变化可观察，恢复后可继续收发 |

真实联调需要人工 SeaTalk 凭证和测试 Bot App，不纳入默认 CI。

## 5. 执行命令

默认命令以 Hermes 官方项目的 Python 工具链为准。若 plugin 仓库单独维护 `pyproject.toml`，优先在 plugin 仓库根目录执行：

```bash
uv run pytest
```

按测试范围执行：

```bash
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/unit/test_runtime_patches.py
uv run pytest tests/integration/test_relay_mode.py
uv run pytest tests/integration/test_webhook_mode.py
```

建议在 CI 中至少运行：

```bash
uv run pytest tests/unit tests/integration
```

真实 SeaTalk 联调不使用默认命令触发，应由人工在具备凭证的测试环境执行。

## 6. 覆盖矩阵

| WBS | 自动化用例 | 人工联调用例 |
| --- | --- | --- |
| W-00 | T-00 | 无 |
| W-01 | T-01 | E-01, E-09 |
| W-02 | T-02 | E-04, E-08 |
| W-03 | T-03 | E-04, E-05, E-08 |
| W-04 | T-04 | E-01, E-02, E-03, E-09 |
| W-05 | T-05 | E-01, E-02, E-03, E-09 |
| W-06 | T-06 | E-02, E-03, E-08 |
| W-07 | T-07 | E-06, E-07 |
| W-08 | T-08 | E-04, E-05 |
| W-09 | T-09 | E-01 |
| W-10 | T-10 | 无 |
| W-11 | 无 | E-01 到 E-09 |

## 7. 退出标准

自动化测试退出标准：

- W-00 到 W-10 对应测试全部通过。
- 关键配置矩阵覆盖 relay/webhook、enabled/disabled、配置缺失、runtime health 缺失。
- monkey patch 幂等和内置平台回归测试通过。
- 测试可以在无 SeaTalk 凭证环境下运行。

真实联调退出标准：

- 至少一种入站模式完成端到端验证。
- 出站发送、home channel、用户鉴权、群过滤均通过。
- 文件或图片路径完成验证或明确记录不可支持原因。
- 联调中发现的 TD 偏差已回写到设计文档或实现 issue。

## 8. 主要风险

| 风险 | 测试应对 |
| --- | --- |
| Hermes 官方版本调整内部函数签名 | T-08 覆盖所有 runtime patch 入口，失败时直接暴露兼容性问题 |
| SeaTalk 外部 API 不稳定或凭证不可用 | 自动化使用 mock server；真实验证独立记录 |
| 鉴权边界被误解 | T-07 和 E-06/E-07 分别覆盖用户 allowlist 与群过滤 |
| relay/webhook 状态语义混淆 | T-01、T-04、T-05、E-09 同时覆盖 static 与 runtime 状态 |
| 测试污染 Hermes 全局状态 | T-10 要求 env、registry、patch 状态全部隔离 |
