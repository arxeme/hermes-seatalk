---
标题: Hermes SeaTalk Plugin 测试报告
状态: draft
更新日期: 2026-05-05
参考材料:
  - Hermes SeaTalk Plugin 技术设计 (../spec/td_hermes-seatalk-plugin_zh.md)
  - Hermes SeaTalk Plugin 工作分解结构 (../spec/wbs_hermes-seatalk-plugin_zh.md)
  - Hermes SeaTalk Plugin 测试计划 (./tp_hermes-seatalk-plugin_zh.md)
  - Hermes SeaTalk Plugin 真实联调 Runbook (./e2e_hermes-seatalk-plugin_runbook_zh.md)
  - Hermes SeaTalk Plugin 真实联调测试报告 (./tr_hermes-seatalk-plugin_e2e_zh.md)
文档摘要: 记录 Hermes SeaTalk Plugin 各 checkpoint 的自动化测试结果、覆盖率和待联调项。
---

# TR: Hermes SeaTalk Plugin

## 1. 当前结论

当前已完成 checkpoint 1、checkpoint 2、checkpoint 3 和 checkpoint 4 的实现与自动化验证：

- W-00 Plugin 包骨架与安装入口：PASS
- W-01 Plugin 注册与平台状态语义：PASS
- W-02 SeaTalk OpenAPI 客户端：PASS
- W-03 Hermes 出站适配器：PASS
- W-04 Webhook 入站模式：PASS
- W-05 Relay 入站模式：PASS
- W-06 入站标准化与调度：PASS
- W-07 鉴权与群过滤：PASS
- W-08 Hermes 兼容性补丁：PASS
- W-09 配置、安装与运维文档：PASS
- W-10 自动化测试集：PASS
- W-11 真实 SeaTalk 联调验证：RUNBOOK READY，真实 E2E 执行 PENDING

本 TR 采用滚动记录方式：后续每完成一个 checkpoint，在同一文件追加对应测试结果、回归命令和未覆盖项。

## 2. 测试环境

| 项目 | 内容 |
| --- | --- |
| 工作目录 | `/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk` |
| Python 环境 | plugin repo 有 `pyproject.toml`；当前测试仍复用 sibling `../../hermes-agent` 的 `uv` 环境 |
| 测试框架 | `pytest`、`pytest-asyncio` |
| 外部依赖 | SeaTalk OpenAPI 使用 fake session/mock response 离线验证；W-11 真实联调仍需真实 SeaTalk 服务 |

说明：当前 plugin repo 尚未建立独立 dev/test 虚拟环境，因此测试命令通过 `uv run --directory ../../hermes-agent` 复用 hermes-agent 的依赖环境执行。

## 3. 测试执行记录

执行命令：

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --directory ../../hermes-agent pytest \
  ../openclaw/hermes-seatalk/tests/test_w00_plugin_skeleton.py \
  ../openclaw/hermes-seatalk/tests/test_w01_registration.py \
  ../openclaw/hermes-seatalk/tests/test_w02_openapi_client.py \
  ../openclaw/hermes-seatalk/tests/test_w03_outbound_adapter.py \
  ../openclaw/hermes-seatalk/tests/test_w04_webhook.py \
  ../openclaw/hermes-seatalk/tests/test_w05_relay.py
```

执行结果：

```text
rootdir: /Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk
configfile: pyproject.toml
collected 47 items

../openclaw/hermes-seatalk/tests/test_w00_plugin_skeleton.py .....       [ 10%]
../openclaw/hermes-seatalk/tests/test_w01_registration.py ........       [ 27%]
../openclaw/hermes-seatalk/tests/test_w02_openapi_client.py ...........  [ 51%]
../openclaw/hermes-seatalk/tests/test_w03_outbound_adapter.py .......... [ 72%]
../openclaw/hermes-seatalk/tests/test_w04_webhook.py .......             [ 87%]
../openclaw/hermes-seatalk/tests/test_w05_relay.py ......                [100%]

47 passed in 0.61s
```

## 4. WBS 任务结果

### W-00 Plugin 包骨架与安装入口

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| plugin manifest 可被识别 | PASS | `tests/test_w00_plugin_skeleton.py` |
| import plugin 不触发注册副作用 | PASS | `tests/test_w00_plugin_skeleton.py` |
| `register(ctx)` 可导入 | PASS | `tests/test_w00_plugin_skeleton.py` |
| loader-style package import 可工作 | PASS | `tests/test_w00_plugin_skeleton.py` |
| `env.example` 覆盖必需配置且不含真实 secret | PASS | `tests/test_w00_plugin_skeleton.py` |

当前交付物：

- `plugin.yaml`
- `pyproject.toml`
- root `__init__.py`
- root `adapter.py` loader shim
- `hermes_seatalk/__init__.py`
- `hermes_seatalk/adapter.py`
- `requirements.txt`
- `env.example`
- `.gitignore`
- `README.md`

### W-01 Plugin 注册与平台状态语义

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| 最小 relay 配置注册平台 | PASS | `tests/test_w01_registration.py` |
| 缺少 credentials 时失败 | PASS | `tests/test_w01_registration.py` |
| relay 模式要求 `SEATALK_RELAY_URL` | PASS | `tests/test_w01_registration.py` |
| webhook 模式不要求 relay URL | PASS | `tests/test_w01_registration.py` |
| `_is_seatalk_connected` 与 `_validate_seatalk_config` 一致 | PASS | `tests/test_w01_registration.py` |
| runtime health 不影响 adapter 创建 | PASS | `tests/test_w01_registration.py` |
| invalid mode 被拒绝 | PASS | `tests/test_w01_registration.py` |
| `register(ctx)` 幂等 | PASS | `tests/test_w01_registration.py` |

当前交付物：

- `register(ctx)` 中的 SeaTalk platform 注册逻辑
- `check_seatalk_requirements()`
- `_validate_seatalk_config()`
- `_is_seatalk_connected()`
- `_seatalk_setup_wizard()` 基础 TUI 配置入口

### W-02 SeaTalk OpenAPI 客户端

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| token 获取成功并缓存 | PASS | `tests/test_w02_openapi_client.py` |
| token 过期刷新失败不污染旧状态 | PASS | `tests/test_w02_openapi_client.py` |
| 发送文本 payload、target、headers 符合协议 | PASS | `tests/test_w02_openapi_client.py` |
| native image/file payload base64、filename、tag 正确 | PASS | `tests/test_w02_openapi_client.py` |
| rate limit/auth/target/network/protocol 错误映射到统一异常 | PASS | `tests/test_w02_openapi_client.py` |
| app secret、access token、signing secret 日志脱敏 | PASS | `tests/test_w02_openapi_client.py` |
| email lookup 只接受 active employee，并缓存正负结果 | PASS | `tests/test_w02_openapi_client.py` |

当前交付物：

- `hermes_seatalk/client.py`
- `SeaTalkOpenAPIClient`
- `SeaTalkError` 及其子类
- token cache / refresh / `code=100` retry / `code=101` backoff retry
- email -> employee_code cache
- text/image/file message payload helper
- 本地文件 base64 native media helper
- 日志脱敏 helper

### W-03 Hermes 出站适配器

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| home channel 发送 | PASS | `tests/test_w03_outbound_adapter.py` |
| 指定 channel 发送 | PASS | `tests/test_w03_outbound_adapter.py` |
| 指定 thread 发送 | PASS | `tests/test_w03_outbound_adapter.py` |
| 长文本按 SeaTalk 限制分段且顺序稳定 | PASS | `tests/test_w03_outbound_adapter.py` |
| 图片和文件 native payload 正确 | PASS | `tests/test_w03_outbound_adapter.py` |
| OpenAPI 发送失败回传 `SendResult` | PASS | `tests/test_w03_outbound_adapter.py` |
| coalescer 默认合并同一 `(chat_id, thread_id)` 文本 | PASS | `tests/test_w03_outbound_adapter.py` |
| coalescer 按 thread 隔离，关闭开关生效 | PASS | `tests/test_w03_outbound_adapter.py` |
| shutdown flush，media 绕过 coalescer | PASS | `tests/test_w03_outbound_adapter.py` |
| target parser 覆盖 employee/email/group/thread 格式 | PASS | `tests/test_w03_outbound_adapter.py` |

当前交付物：

- `hermes_seatalk/targets.py`
- `hermes_seatalk/coalescer.py`
- `SeaTalkAdapter.send()`
- `SeaTalkAdapter.send_typing()`
- `SeaTalkAdapter.send_image()` / `send_image_file()` / `send_document()`
- home channel / thread metadata / email target resolution
- outbound text chunking
- outbound coalescer and shutdown flush

### W-04 Webhook 入站模式

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| 合法事件进入标准 dispatch 入口 | PASS | `tests/test_w04_webhook.py` |
| 签名无效拒绝且不 dispatch | PASS | `tests/test_w04_webhook.py` |
| `event_verification` 签名有效时返回 challenge | PASS | `tests/test_w04_webhook.py` |
| malformed payload 返回 400 | PASS | `tests/test_w04_webhook.py` |
| 普通事件快速 ack，不等待后台 dispatch | PASS | `tests/test_w04_webhook.py` |
| webhook dispatch 更新 adapter connected 状态 | PASS | `tests/test_w04_webhook.py` |
| `event_verification` 签名无效时不返回 challenge | PASS | `tests/test_w04_webhook.py` |

当前交付物：

- `hermes_seatalk/webhook.py`
- raw body + `Signature` 校验
- 1 MB body 限制
- `event_verification` challenge
- 普通事件异步 dispatch
- adapter webhook connect/disconnect

### W-05 Relay 入站模式

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| relay WebSocket 建连并完成 auth | PASS | `tests/test_w05_relay.py` |
| relay event 进入同一 dispatch 入口 | PASS | `tests/test_w05_relay.py` |
| malformed relay message 记录后继续运行 | PASS | `tests/test_w05_relay.py` |
| relay 断线后按 backoff 重连 | PASS | `tests/test_w05_relay.py` |
| heartbeat timeout 更新状态并触发重连路径 | PASS | `tests/test_w05_relay.py` |
| shutdown 能退出 relay client | PASS | `tests/test_w05_relay.py` |

当前交付物：

- `hermes_seatalk/relay.py`
- relay WebSocket auth
- `auth_ok` / `auth_fail` / `event` / `ping` / `replaced` 协议处理
- heartbeat timeout
- reconnect backoff
- adapter relay connect/disconnect

### W-06 入站标准化与调度

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| webhook/relay 同构，生成相同 Hermes input schema | PASS | `tests/test_w06_dispatcher.py` |
| 同一用户同一 channel/thread 的 session key 稳定 | PASS | `tests/test_w06_dispatcher.py` |
| 相同 SeaTalk event id 重复投递只触发一次 | PASS | `tests/test_w06_dispatcher.py` |
| 连续短消息按 TD debounce 规则合并后调度 | PASS | `tests/test_w06_dispatcher.py` |
| quoted message 保留到正文前缀和 reply metadata | PASS | `tests/test_w06_dispatcher.py` |
| 附件下载失败时文本/占位仍进入 agent，错误写入 metadata | PASS | `tests/test_w06_dispatcher.py` |

当前交付物：

- `hermes_seatalk/dispatcher.py`
- `SeaTalkEventDispatcher`
- `app_id:event_id` 去重缓存
- DM/group/thread event normalizer
- inbound debounce buffer
- quoted message resolve fallback
- 入站 media 下载与失败降级
- adapter webhook/relay 共享 dispatcher 入口

### W-07 鉴权与群过滤

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| 有 email 时优先用 email 作为 `source.user_id` | PASS | `tests/test_w07_authorization.py` |
| 无 email 时 fallback 到 employee code | PASS | `tests/test_w07_authorization.py` |
| 不在 allowlist 的用户经 Hermes gateway auth 被拒绝 | PASS | `tests/test_w07_authorization.py` |
| group allowlist 命中时继续执行用户鉴权路径 | PASS | `tests/test_w07_authorization.py` |
| group allowlist 未命中时 dispatcher 预过滤拒绝 | PASS | `tests/test_w07_authorization.py` |
| 拒绝日志包含 channel 和 reason，不泄漏 secret 或 sender email | PASS | `tests/test_w07_authorization.py` |

当前交付物：

- `MessageEvent.source.user_id` email 优先 / employee fallback
- `MessageEvent.source.user_id_alt` 保留 employee code
- `SEATALK_GROUP_ALLOWED_USERS` channel pre-filter
- 基于 Hermes `PlatformEntry.allowed_users_env` 的 gateway auth 验证
- group 拒绝日志脱敏

### W-08 Hermes 兼容性补丁

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| `send_message(target="seatalk")` 可路由到 SeaTalk adapter | PASS | `tests/test_w08_runtime_patch.py` |
| `_send_to_platform` 支持 SeaTalk 并保留 thread/media | PASS | `tests/test_w08_runtime_patch.py` |
| `get_home_channel("seatalk")` 返回 `SEATALK_HOME_CHANNEL` | PASS | `tests/test_w08_runtime_patch.py` |
| `SEATALK_HOME_CHANNEL_THREAD_ID` 被保留 | PASS | `tests/test_w08_runtime_patch.py` |
| cron target 支持 `seatalk` home channel | PASS | `tests/test_w08_runtime_patch.py` |
| runtime patch 幂等，不重复包装 | PASS | `tests/test_w08_runtime_patch.py` |
| Slack/Discord 内置平台 target parser 行为不变 | PASS | `tests/test_w08_runtime_patch.py` |
| SeaTalk target parser 覆盖 employee/email/group/thread 全格式 | PASS | `tests/test_w08_runtime_patch.py` |

当前交付物：

- `_patch_cron_scheduler()`
- `_patch_send_message_tool()`
- `_patch_send_to_platform()`
- `_patch_home_channel()`
- `_seatalk_send_to_platform()`
- `register(ctx)` 中四处 patch 的幂等调用

### W-09 配置、安装与运维文档

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| README 命令可执行 | PASS | `tests/test_w09_operations_docs.py` |
| enable/restart 说明准确 | PASS | `tests/test_w09_operations_docs.py` |
| TUI 出现条件 | PASS | `tests/test_w09_operations_docs.py` |
| setup wizard 顺序 | PASS | `tests/test_w09_operations_docs.py` |
| relay 互斥配置 | PASS | `tests/test_w09_operations_docs.py` |
| webhook 互斥配置 | PASS | `tests/test_w09_operations_docs.py` |
| 鉴权边界清晰 | PASS | `tests/test_w09_operations_docs.py` |
| 排查路径可用 | PASS | `tests/test_w09_operations_docs.py` |

当前交付物：

- `README.md` 安装、启用、TUI、模式互斥、状态与排查说明
- `env.example` 可选 coalescing/debounce 配置示例
- `_seatalk_setup_wizard()` 补充 group mention policy 可选项

### W-10 自动化测试集

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| 测试可离线运行 | PASS | `tests/test_w10_test_quality.py` |
| env 隔离 | PASS | `tests/test_w10_test_quality.py`, `tests/conftest.py` |
| registry 隔离 | PASS | `tests/test_w10_test_quality.py`, `tests/conftest.py` |
| patch 状态隔离 | PASS | `tests/test_w10_test_quality.py`, `tests/conftest.py` |
| 重复运行稳定 | PASS | 连续两次完整 suite 均为 `83 passed` |

当前交付物：

- pytest autouse fixture 隔离 SeaTalk/Gateway env
- pytest autouse fixture 隔离 Hermes `platform_registry`
- pytest autouse fixture 隔离 `send_message`、home channel、cron runtime patch
- W-09/W-10 自动化测试
- W-07 测试修正为独立注册 `seatalk` platform，不依赖前序测试泄漏状态

### W-11 真实 SeaTalk 联调验证

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| E-01 Bot App 配置 | PENDING | `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` |
| E-02 用户私聊入站 | PENDING | `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` |
| E-03 群聊入站 | PENDING | `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` |
| E-04 出站工具调用 | PENDING | `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` |
| E-05 home channel | PENDING | `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` |
| E-06 未授权用户 | PENDING | `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` |
| E-07 未授权群 | PENDING | `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` |
| E-08 文件或图片 | PENDING | `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` |
| E-09 relay/webhook runtime health | PENDING | `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` |

当前交付物：

- 真实联调 runbook
- Bot App 配置摘要模板
- E-01 到 E-09 结果记录表
- 问题回流路径

## 5. Checkpoint 3 回归记录

执行命令：

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --directory ../../hermes-agent pytest \
  ../openclaw/hermes-seatalk/tests/test_w00_plugin_skeleton.py \
  ../openclaw/hermes-seatalk/tests/test_w01_registration.py \
  ../openclaw/hermes-seatalk/tests/test_w02_openapi_client.py \
  ../openclaw/hermes-seatalk/tests/test_w03_outbound_adapter.py \
  ../openclaw/hermes-seatalk/tests/test_w04_webhook.py \
  ../openclaw/hermes-seatalk/tests/test_w05_relay.py \
  ../openclaw/hermes-seatalk/tests/test_w06_dispatcher.py \
  ../openclaw/hermes-seatalk/tests/test_w07_authorization.py \
  ../openclaw/hermes-seatalk/tests/test_w08_runtime_patch.py
```

执行结果：

```text
collected 67 items

../openclaw/hermes-seatalk/tests/test_w00_plugin_skeleton.py .....       [  7%]
../openclaw/hermes-seatalk/tests/test_w01_registration.py ........       [ 19%]
../openclaw/hermes-seatalk/tests/test_w02_openapi_client.py ...........  [ 35%]
../openclaw/hermes-seatalk/tests/test_w03_outbound_adapter.py .......... [ 50%]
../openclaw/hermes-seatalk/tests/test_w04_webhook.py .......             [ 61%]
../openclaw/hermes-seatalk/tests/test_w05_relay.py ......                [ 70%]
../openclaw/hermes-seatalk/tests/test_w06_dispatcher.py ......           [ 79%]
../openclaw/hermes-seatalk/tests/test_w07_authorization.py ......        [ 88%]
../openclaw/hermes-seatalk/tests/test_w08_runtime_patch.py ........      [100%]

67 passed in 1.33s
```

## 6. Checkpoint 4 回归记录

执行命令：

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --directory ../../hermes-agent pytest \
  ../openclaw/hermes-seatalk/tests
```

执行结果：

```text
collected 83 items

../openclaw/hermes-seatalk/tests/test_w00_plugin_skeleton.py .....       [  6%]
../openclaw/hermes-seatalk/tests/test_w01_registration.py ........       [ 15%]
../openclaw/hermes-seatalk/tests/test_w02_openapi_client.py ...........  [ 28%]
../openclaw/hermes-seatalk/tests/test_w03_outbound_adapter.py .......... [ 40%]
../openclaw/hermes-seatalk/tests/test_w04_webhook.py .......             [ 49%]
../openclaw/hermes-seatalk/tests/test_w05_relay.py ......                [ 56%]
../openclaw/hermes-seatalk/tests/test_w06_dispatcher.py ......           [ 63%]
../openclaw/hermes-seatalk/tests/test_w07_authorization.py ......        [ 71%]
../openclaw/hermes-seatalk/tests/test_w08_runtime_patch.py ........      [ 80%]
../openclaw/hermes-seatalk/tests/test_w09_operations_docs.py ........    [ 90%]
../openclaw/hermes-seatalk/tests/test_w10_test_quality.py ........       [100%]

83 passed in 1.15s
```

重复执行结果：

```text
83 passed in 1.20s
```

覆盖率命令：

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with coverage --directory ../../hermes-agent \
  coverage run -m pytest ../openclaw/hermes-seatalk/tests

uv run --with coverage --directory ../../hermes-agent \
  coverage report -m --include '../openclaw/hermes-seatalk/hermes_seatalk/*'
```

覆盖率结果摘要：

```text
Name                      Stmts   Miss  Cover
------------------------------------------------
hermes_seatalk/__init__.py    2      0   100%
hermes_seatalk/adapter.py   435    123    72%
hermes_seatalk/client.py    282     72    74%
hermes_seatalk/coalescer.py  90     18    80%
hermes_seatalk/dispatcher.py 318     74    77%
hermes_seatalk/relay.py     112     19    83%
hermes_seatalk/targets.py    37      8    78%
hermes_seatalk/webhook.py    75      5    93%
------------------------------------------------
TOTAL                      1351    319    76%
```

## 7. 未覆盖项 / Deferred

| 项目 | 状态 | 原因 |
| --- | --- | --- |
| 真实 SeaTalk OpenAPI E2E | PENDING | 需要真实 Bot App credentials 和外部网络；执行入口见 `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` |
| 真实 SeaTalk webhook/relay E2E | PENDING | 需要真实 callback URL / relay service / Bot App；执行入口见 `docs/test/e2e_hermes-seatalk-plugin_runbook_zh.md` |
| plugin repo 独立 test env | PENDING | 已有 `pyproject.toml`，但当前仍复用 `../../hermes-agent` 的 `uv` 环境运行 pytest |
| W-11 真实联调执行 | PENDING | runbook 已准备；需要 HITL 提供真实 SeaTalk Bot App、用户、群和模式链路 |

## 8. 回归命令

当前最小回归命令：

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --directory ../../hermes-agent pytest \
  ../openclaw/hermes-seatalk/tests/test_w00_plugin_skeleton.py \
  ../openclaw/hermes-seatalk/tests/test_w01_registration.py \
  ../openclaw/hermes-seatalk/tests/test_w02_openapi_client.py \
  ../openclaw/hermes-seatalk/tests/test_w03_outbound_adapter.py \
  ../openclaw/hermes-seatalk/tests/test_w04_webhook.py \
  ../openclaw/hermes-seatalk/tests/test_w05_relay.py \
  ../openclaw/hermes-seatalk/tests/test_w06_dispatcher.py \
  ../openclaw/hermes-seatalk/tests/test_w07_authorization.py \
  ../openclaw/hermes-seatalk/tests/test_w08_runtime_patch.py
```

当前完整回归命令：

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --directory ../../hermes-agent pytest \
  ../openclaw/hermes-seatalk/tests
```
