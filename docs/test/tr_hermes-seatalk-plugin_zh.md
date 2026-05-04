# TR: Hermes SeaTalk Plugin

更新时间：2026-05-04

## 1. 当前结论

当前已完成 checkpoint 1 和 checkpoint 2 的实现与自动化验证：

- W-00 Plugin 包骨架与安装入口：PASS
- W-01 Plugin 注册与平台状态语义：PASS
- W-02 SeaTalk OpenAPI 客户端：PASS
- W-03 Hermes 出站适配器：PASS
- W-04 Webhook 入站模式：PASS
- W-05 Relay 入站模式：PASS

本 TR 采用滚动记录方式：后续每完成一个 checkpoint，在同一文件追加对应测试结果、回归命令和未覆盖项。

## 2. 测试环境

| 项目 | 内容 |
| --- | --- |
| 工作目录 | `/Users/yuy/Work/go/gitlab.garena.com/ai-agent/voyager/openclaw/hermes-seatalk` |
| Python 环境 | plugin repo 有 `pyproject.toml`；当前测试仍复用 sibling `../../hermes-agent` 的 `uv` 环境 |
| 测试框架 | `pytest`、`pytest-asyncio` |
| 外部依赖 | SeaTalk OpenAPI 使用 fake session/mock response 离线验证，未访问真实 SeaTalk 服务 |

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

## 5. 未覆盖项 / Deferred

| 项目 | 状态 | 原因 |
| --- | --- | --- |
| 真实 SeaTalk OpenAPI E2E | PENDING | 需要真实 Bot App credentials 和外部网络 |
| 真实 SeaTalk webhook/relay E2E | PENDING | 需要真实 callback URL / relay service / Bot App |
| plugin repo 独立 test env | PENDING | 已有 `pyproject.toml`，但当前仍复用 `../../hermes-agent` 的 `uv` 环境运行 pytest |
| W-06 入站事件 dispatcher | PENDING | 尚未实现 |
| W-07 授权与 group channel 过滤 | PENDING | 尚未实现 |
| W-08 Hermes send_message/cron 集成 | PENDING | 尚未实现 |
| W-09 setup/status 用户引导闭环 | PENDING | 仅有 W-01 基础 setup wizard，完整 status/list 仍待实现 |
| W-10 自动化测试集 | PENDING | 当前已有 W-00/W-01/W-02 测试，完整 suite 待后续任务补齐 |
| W-11 文档与发布 | PENDING | 尚未进入发布验证 |

## 6. 回归命令

当前最小回归命令：

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --directory ../../hermes-agent pytest \
  ../openclaw/hermes-seatalk/tests/test_w00_plugin_skeleton.py \
  ../openclaw/hermes-seatalk/tests/test_w01_registration.py \
  ../openclaw/hermes-seatalk/tests/test_w02_openapi_client.py \
  ../openclaw/hermes-seatalk/tests/test_w03_outbound_adapter.py \
  ../openclaw/hermes-seatalk/tests/test_w04_webhook.py \
  ../openclaw/hermes-seatalk/tests/test_w05_relay.py
```
