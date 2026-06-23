# SOP 开放平台开发者接入指南

本文基于 [`seatalk-oapi-sdk-go`](./seatalk-oapi-sdk-go) 和 [`seatalk-oapi-sdk-py`](./seatalk-oapi-sdk-py) 的当前实现整理，面向需要接入 `seatalk open platform` WebSocket 协议的 SOP 开放平台开发者。

## 1. 你会接入到什么能力

两个 SDK 都封装了同一套 developer bot WebSocket 协议，核心能力一致：

- 使用 `app_id` / `app_secret` 发起 `register`
- 注册成功后拿到会话 `token`
- 持续接收平台推送的 `event`
- 在事件带有 `callback_id` 且处理成功后自动发送 `ack`
- 在连接存活期间自动发送应用层 `ping`，并静默消费 `pong`
- 支持默认日志打印、自定义 envelope 日志、自定义非法帧日志
- 支持通用事件处理和 typed event handler

当前默认 WebSocket 地址常量是 `wss://ws-openapi.haiserve.com/ws/bot`。

## 2. SDK 目录与语言选择

### Go SDK

- 路径：[`seatalk-oapi-sdk-go`](./seatalk-oapi-sdk-go)
- 主要类型：
  - `Client`
  - `EventDispatcher`
  - `Envelope`
  - 各类 typed event 结构体

### Python SDK

- 路径：[`seatalk-oapi-sdk-py`](./seatalk-oapi-sdk-py)
- 特点：
  - 纯标准库实现
  - 不依赖第三方 WebSocket 包
  - API 命名尽量与 Go SDK 对齐

如果你的机器人服务本身是 Go 服务，优先使用 Go SDK；如果你要快速验证接入链路、做轻量回调服务或脚本化消费事件，Python SDK 会更方便。

## 3. 接入前准备

开始前请确认你已经拿到：

- 开放平台分配的 `app_id`
- 开放平台分配的 `app_secret`
- 对应环境的 WebSocket 接入地址, 默认wss://ws-openapi.haiserve.com/ws/bot

建议你先明确两个问题：

1. 你要消费哪些事件类型
2. 你的业务处理失败时，是否需要让平台重试

第二点很重要。两个 SDK 的自动 `ack` 都只发生在“事件处理成功”之后：

- Go：handler 返回 `nil` 时自动 `ack`
- Python：handler 正常返回、没有抛异常时自动 `ack`

如果你的业务处理失败，不要吞掉错误；否则 SDK 会认为处理成功并自动确认该事件。

## 4. 协议交互模型

整体流程如下：

1. 客户端建立 WebSocket 连接
2. 客户端发送 `register`
3. 平台返回 `register` 响应
4. 响应成功后，SDK 保存 `token`
5. 平台持续下发 `event`
6. SDK 分发给通用 handler 或 typed handler
7. 如果事件包含 `callback_id` 且 handler 成功，SDK 自动发送 `ack`
8. SDK 按心跳间隔持续发送 `ping`
9. 平台返回 `pong`
10. 如平台主动断连，可能下发 `kick`

### 支持的命令

- `register`
- `ack`
- `ping`
- `pong`
- `kick`
- `event`

### 注册成功后能拿到什么

`register` 成功后，SDK 会返回：

- `app_id`
- `token`
- `heartbeat_interval`
- `heartbeat_timeout`

当前两个 SDK 都会使用 `heartbeat_interval` 作为优先心跳间隔；如果服务端没有返回该值，则回退到本地默认值 `15s`。`heartbeat_timeout` 会被解析并暴露在返回结果里，但 SDK 当前不会基于它主动做额外超时控制。

## 5. 快速开始

### Go 最小示例

```go
package main

import (
	"context"
	"log"

	seatalkoapisdk "git.garena.com/seatalk/seatalk-oapi-sdk-go"
)

func main() {
	dispatcher := seatalkoapisdk.NewEventDispatcher().
		OnMessageFromBotSubscriber(func(ctx context.Context, event *seatalkoapisdk.MessageFromBotSubscriberEvent) error {
			if event.Event.Message.Tag == seatalkoapisdk.MessageTagText && event.Event.Message.Text != nil {
				log.Printf("subscriber text=%s", event.Event.Message.Text.Content)
			}
			return nil
		})

	client := seatalkoapisdk.NewClient(
		"your-app-id",
		"your-app-secret",
		seatalkoapisdk.WithWebSocketURL("wss://your-websocket-endpoint"),
		seatalkoapisdk.WithEventDispatcher(dispatcher),
	)
	defer client.Close()

	if err := client.Run(context.Background()); err != nil {
		log.Fatal(err)
	}
}
```

### Python 最小示例

```python
from seatalk_oapi_sdk import Client, EventDispatcher, MESSAGE_TAG_TEXT


def handle_message(event):
    message = event.event.message
    if message.tag == MESSAGE_TAG_TEXT and message.text is not None:
        print("subscriber text:", message.text.content)


dispatcher = EventDispatcher().on_message_from_bot_subscriber(handle_message)

client = Client(
    app_id="your-app-id",
    app_secret="your-app-secret",
    ws_url="wss://your-websocket-endpoint",
    dispatcher=dispatcher,
)

try:
    client.run()
finally:
    client.close()
```

## 6. 推荐的开发方式

### 方式一：先用默认 dispatcher 看原始 envelope

适合刚接入时确认平台是否正常推送事件。

- Go 示例：[`seatalk-oapi-sdk-go/examples/basic_client/main.go`](./seatalk-oapi-sdk-go/examples/basic_client/main.go)
- Python 示例：[`seatalk-oapi-sdk-py/examples/basic_client.py`](./seatalk-oapi-sdk-py/examples/basic_client.py)

默认行为：

- 收到合法 envelope 时，SDK 会格式化打印整包内容
- 收到非 JSON 文本帧时，SDK 会打印非法帧信息

### 方式二：切到 typed handler 做正式业务处理

适合进入业务开发阶段，直接按事件类型读取结构化字段。

- Go 示例：[`seatalk-oapi-sdk-go/examples/typed_handlers/main.go`](./seatalk-oapi-sdk-go/examples/typed_handlers/main.go)
- Python 示例：[`seatalk-oapi-sdk-py/examples/typed_handlers.py`](./seatalk-oapi-sdk-py/examples/typed_handlers.py)

### 方式三：替换默认日志

适合接入你自己的观测体系、日志平台或本地调试格式。

- Go 示例：[`seatalk-oapi-sdk-go/examples/custom_logging/main.go`](./seatalk-oapi-sdk-go/examples/custom_logging/main.go)
- Python 示例：[`seatalk-oapi-sdk-py/examples/custom_logging.py`](./seatalk-oapi-sdk-py/examples/custom_logging.py)

## 7. 支持的事件类型

两个 SDK 当前都支持以下 8 类 typed event：

| 事件类型 | 说明 | 常见关键字段 |
| --- | --- | --- |
| `user_enter_chatroom_with_bot` | 用户进入机器人会话 | `seatalk_id` `employee_code` `email` |
| `message_from_bot_subscriber` | 订阅者给机器人发送消息 | `seatalk_id` `message.tag` `message.text/image/file/video` |
| `new_mentioned_message_received_from_group_chat` | 群聊中 @ 到机器人 | `group_id` `message.sender` `message.text.plain_text` |
| `interactive_message_click` | 用户点击交互消息 | `message_id` `value` `seatalk_id` `group_id` `thread_id` |
| `new_message_received_from_thread` | Thread 中收到新消息 | `group_id` `message.thread_id` `message.tag` |
| `bot_added_to_group_chat` | 机器人被拉入群聊 | `group.group_id` `group.group_name` `inviter` |
| `bot_removed_from_group_chat` | 机器人被移出群聊 | `group_id` `remover` |
| `group_chat_converted_to_external_group` | 群聊转为外部群 | `group_id` `operator` |

事件详情见: https://open.seatalk.io/docs/list-of-events

## 8. 消息体字段说明

### 8.1 `message_from_bot_subscriber`

消息对象 `message` 当前支持的 `tag`：

- `text`
- `image`
- `file`
- `video`
- `combined_forwarded_chat_history`

其中：

- `text` 对应 `message.text.content`
- `image` 对应 `message.image.content`
- `file` 对应 `message.file.content` 与 `message.file.filename`
- `video` 对应 `message.video.content`

`combined_forwarded_chat_history` 常量已在两个 SDK 中暴露，但当前 typed 结构没有为它补充专门字段；如果你需要处理这类消息，建议先通过默认 envelope 日志确认原始数据格式，再决定是否走通用事件解析。

### 8.2 `new_mentioned_message_received_from_group_chat`

文本消息常用字段：

- `message.text.plain_text`
- `message.text.mentioned_list`
- `message.sender`
- `message.thread_id`

### 8.3 `new_message_received_from_thread`

Thread 消息常用字段：

- `message.thread_id`
- `message.tag`
- `message.text.plain_text`
- `message.mentioned_list`

## 9. Handler 注册方式

### Go

Go SDK 通过链式 API 注册 handler，例如：

```go
dispatcher := seatalkoapisdk.NewEventDispatcher().
	OnMessageFromBotSubscriber(handleSubscriberMessage).
	OnInteractiveMessageClick(handleInteractiveClick).
	OnKick(handleKick).
	OnEnvelope(handleEnvelope).
	OnInvalidFrame(handleInvalidFrame)
```

你可以同时注册：

- `OnEvent`：通用事件处理
- 各类 typed handler：结构化事件处理
- `OnEnvelope`：每个合法 envelope 的统一拦截
- `OnInvalidFrame`：非法 JSON 帧处理
- `OnKick`：平台踢下线处理

### Python

Python SDK 提供 snake_case 和 Go 风格别名两套 API：

```python
dispatcher = (
    EventDispatcher()
    .on_message_from_bot_subscriber(handle_subscriber_message)
    .on_interactive_message_click(handle_interactive_click)
    .on_kick(handle_kick)
    .on_envelope(handle_envelope)
    .on_invalid_frame(handle_invalid_frame)
)
```

如果你希望与 Go 文档或已有习惯保持一致，也可以使用 `OnMessageFromBotSubscriber` 这一类别名方法。

## 10. 自动 ack 机制

这是接入时最容易忽略、也最关键的一点。

自动 `ack` 的触发条件是：

- 收到的是 `event`
- 事件头里带有 `callback_id`
- 至少有一个 handler 真正处理了该事件
- 处理过程没有报错

这意味着：

- 只注册 `OnEnvelope` / `on_envelope` 不会触发自动 `ack`
- 只打印日志但不注册通用事件或 typed handler，也不会触发自动 `ack`
- 如果你想自己控制确认时机，可以走手动流程，调用 `Ack(callbackID)`

## 11. 连接与生命周期 API

两个 SDK 的核心方法基本对齐：

| 能力 | Go | Python | 说明 |
| --- | --- | --- | --- |
| 建连并注册 | `Connect(ctx)` | `connect()` | 返回注册结果与 token |
| 开始监听 | `Start(ctx)` | `start()` | 持续读消息并发心跳 |
| 一步运行 | `Run(ctx)` | `run()` | 内部完成 connect + start |
| 手动确认 | `Ack(ctx, callbackID)` | `ack(callback_id)` | 发送 `ack` |
| 主动发心跳 | `Ping(ctx)` | `ping()` | 发送应用层 `ping` |
| 关闭连接 | `Close()` | `close()` | 关闭 WebSocket |

如果你只想快速接入，优先使用 `Run` / `run`。

如果你要把“注册成功后返回 token”“开始消费事件”“优雅退出”拆开管理，使用 `Connect + Start + Close` 更灵活。

## 12. 可配置项

### Go `ClientOption`

Go SDK 支持以下配置：

- `WithWebSocketURL`
- `WithDialer`
- `WithRequestHeader`
- `WithHandshakeTimeout`
- `WithWriteTimeout`
- `WithPingInterval`
- `WithReadLimit`
- `WithEventDispatcher`
- `WithLogger`

适合场景：

- 通过 `WithRequestHeader` 附加额外 HTTP Header
- 通过 `WithHandshakeTimeout` / `WithWriteTimeout` 调整超时
- 通过 `WithPingInterval` 指定本地回退心跳间隔

### Python `Client(...)`

Python SDK 构造参数支持：

- `ws_url`
- `request_headers`
- `handshake_timeout`
- `write_timeout`
- `ping_interval`
- `read_limit`
- `dispatcher`
- `logger`

其中 `request_headers` 与 Go 的 `WithRequestHeader` 作用一致。

关于 `logger`，两边当前实现有一个细微差异：

- Python SDK 会在部分底层收发路径输出调试日志，例如发送应用层 `ping`、收到 WebSocket `ping` 帧
- Go SDK 当前提供了 `WithLogger` 配置入口，但暂未在内部主流程中输出额外日志

所以如果你依赖 SDK 内部日志做排障，Python 侧会更直接；Go 侧更建议通过 `OnEnvelope` / `OnInvalidFrame` 接入你自己的日志方案。

## 13. 错误处理建议

两个 SDK 当前都显式区分了几类常见错误：

- 缺少凭证：`app_id` / `app_secret` 为空
- 重复连接：已经连接又再次 `connect`
- 未连接却发送消息
- 未注册成功却尝试 `ack` / `ping`
- `register` 被平台拒绝：`RegisterError`
- 平台主动踢下线：`KickError`

推荐做法：

1. 将 `RegisterError` 单独记录，便于区分配置错误和网络错误
2. 对 `KickError` 打出平台返回的 `message`
3. 在 handler 中把真正的业务异常向上抛出，避免错误事件被自动确认
4. 优雅退出时始终调用 `Close` / `close`

## 14. 本地联调与示例命令

### Go

```bash
go run ./seatalk-oapi-sdk-go/examples/basic_client \
  --url "wss://ws-openapi.haiserve.com/ws/bot" \
  --app-id "$APP_ID" \
  --app-secret "$APP_SECRET"
```

```bash
go run ./seatalk-oapi-sdk-go/examples/typed_handlers \
  --url "wss://ws-openapi.haiserve.com/ws/bot" \
  --app-id "$APP_ID" \
  --app-secret "$APP_SECRET"
```

### Python

```bash
python3 ./seatalk-oapi-sdk-py/examples/basic_client.py \
  --url "wss://ws-openapi.haiserve.com/ws/bot" \
  --app-id "$APP_ID" \
  --app-secret "$APP_SECRET"
```

```bash
python3 ./seatalk-oapi-sdk-py/examples/typed_handlers.py \
  --url "wss://ws-openapi.haiserve.com/ws/bot" \
  --app-id "$APP_ID" \
  --app-secret "$APP_SECRET"
```

## 15. 一套比较稳妥的接入顺序

建议按下面顺序推进：

1. 用 `basic_client` 连上环境，确认 `register` 能成功
2. 观察默认 envelope 输出，确认实际会收到哪些 `event_type`
3. 只为第一批需要的事件注册 typed handler
4. 在 handler 中先做日志和字段校验，再接业务逻辑
5. 最后再替换为你自己的 envelope / invalid-frame 日志方案

这样做的好处是：协议层问题、字段问题和业务问题会被分层暴露，定位更快。

## 16. 结语

如果你只是要尽快把 SOP 机器人接起来，可以直接从 typed handler 示例开始；如果你还不确定平台会推哪些字段，先跑 `basic_client` 看原始 envelope 会更稳。

这篇文档描述的是当前仓库内 Go/Python SDK 已实现的能力范围；如果开放平台后续新增事件类型或补充消息结构，建议同时更新 SDK 的 typed model 和本接入文档。
