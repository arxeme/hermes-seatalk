# seatalk-oapi-sdk-py

Pure-stdlib Python SDK for the seatalk open platform developer bot WebSocket protocol.

For a Chinese integration guide aimed at SOP open platform developers, see [OPEN_PLATFORM_DEVELOPER_GUIDE.md](OPEN_PLATFORM_DEVELOPER_GUIDE.md).

It mirrors the Go SDK:

- `Client.connect()`, `Client.start()`, `Client.run()`, `Client.ack()`, `Client.close()`
- default pretty-print for every received envelope
- default printing for invalid JSON frames
- typed event handlers
- automatic ack after a generic or typed event handler returns successfully
- application-level `ping` commands while `start()` / `run()` is active; the SDK uses the heartbeat interval returned by `register`, falling back to the local default of 15 seconds; `pong` responses are consumed silently

No third-party package is required. The SDK implements the small WebSocket subset needed by seatalk open platform developer using Python's standard library.

## Requirements

The SDK has no third-party runtime dependencies. `requirements.txt` is kept on
purpose so local setup and CI can still use the standard install flow:

```sh
python3 -m pip install -r requirements.txt
```

## Install

Install the SDK into your current development environment:

```sh
python3 -m pip install -e .
```

If you prefer installing through a requirements file, use:

```sh
python3 -m pip install -r requirements-dev.txt
```

After installation, verify the package import with:

```sh
python3 -c "import seatalk_oapi_sdk; print(seatalk_oapi_sdk.__version__)"
```

## Basic Usage

```python
from seatalk_oapi_sdk import Client, EventDispatcher, MESSAGE_TAG_TEXT


dispatcher = (
    EventDispatcher()
    .on_message_from_bot_subscriber(
        lambda event: print(event.event.message.text.content)
        if event.event.message.tag == MESSAGE_TAG_TEXT and event.event.message.text
        else None
    )
)

client = Client(
    app_id="your-app-id",
    app_secret="your-app-secret",
    ws_url="wss://ws-openapi.haiserve.com/ws/bot",
    dispatcher=dispatcher,
)

try:
    result = client.connect()
    print("registered ok, session token:", result.token)
    client.start()
finally:
    client.close()
```

## Typed Handlers

Available handler methods:

- `on_user_enter_chatroom_with_bot`
- `on_message_from_bot_subscriber`
- `on_new_mentioned_message_received_from_group_chat`
- `on_interactive_message_click`
- `on_new_message_received_from_thread`
- `on_bot_added_to_group_chat`
- `on_bot_removed_from_group_chat`
- `on_group_chat_converted_to_external_group`

For Go-style familiarity, `OnUserEnterChatroomWithBot`, `OnMessageFromBotSubscriber`, etc. are also available as aliases.

## Run Examples

From this directory:

```sh
python3 examples/basic_client.py --app-id "$APP_ID" --app-secret "$APP_SECRET"
python3 examples/typed_handlers.py --app-id "$APP_ID" --app-secret "$APP_SECRET"
python3 examples/custom_logging.py --app-id "$APP_ID" --app-secret "$APP_SECRET"
```

## Tests

```sh
python3 -m unittest discover seatalk-oapi-sdk-py/tests
```
