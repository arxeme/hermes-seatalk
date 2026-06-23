from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seatalk_oapi_sdk import (  # noqa: E402
    COMMAND_EVENT,
    EVENT_TYPE_GROUP_CHAT_CONVERTED_TO_EXTERNAL_GROUP,
    EVENT_TYPE_MESSAGE_FROM_BOT_SUBSCRIBER,
    EVENT_TYPE_USER_ENTER_CHATROOM_WITH_BOT,
    Envelope,
    EventDispatcher,
    GroupChatConvertedToExternalGroupEvent,
    Header,
    MessageFromBotSubscriberEvent,
    UserEnterChatroomWithBotEvent,
)


class FakeClient:
    def __init__(self) -> None:
        self.acks = []

    def ack(self, callback_id: str) -> None:
        self.acks.append(callback_id)


class DispatcherTest(unittest.TestCase):
    def test_typed_event_handler_and_auto_ack(self) -> None:
        seen = []
        client = FakeClient()
        dispatcher = (
            EventDispatcher()
            .on_envelope(None)
            .on_message_from_bot_subscriber(lambda event: seen.append(event))
        )

        dispatcher.dispatch(
            client,
            Envelope(
                cmd=COMMAND_EVENT,
                header=Header(app_id="app-1", callback_id="callback-1"),
                data={
                    "event_id": "event-1",
                    "event_type": EVENT_TYPE_MESSAGE_FROM_BOT_SUBSCRIBER,
                    "timestamp": 1611220944,
                    "app_id": "app-1",
                    "event": {
                        "seatalk_id": "u-1",
                        "employee_code": "e_1",
                        "email": "sample@seatalk.biz",
                        "message": {
                            "message_id": "msg-1",
                            "tag": "text",
                            "text": {"content": "hello"},
                        },
                    },
                },
            ),
        )

        self.assertEqual(client.acks, ["callback-1"])
        self.assertEqual(len(seen), 1)
        event = seen[0]
        self.assertIsInstance(event, MessageFromBotSubscriberEvent)
        self.assertEqual(event.event.message.text.content, "hello")

    def test_generic_event_handler_and_auto_ack(self) -> None:
        seen = []
        client = FakeClient()
        dispatcher = EventDispatcher().on_envelope(None).on_event(lambda event: seen.append(event))

        dispatcher.dispatch(
            client,
            Envelope(
                cmd=COMMAND_EVENT,
                header=Header(app_id="app-1", callback_id="callback-1"),
                data={"hello": "world"},
            ),
        )

        self.assertEqual(client.acks, ["callback-1"])
        self.assertEqual(seen[0].data, {"hello": "world"})

    def test_group_chat_converted_to_external_group_handler_and_auto_ack(self) -> None:
        seen = []
        client = FakeClient()
        dispatcher = (
            EventDispatcher()
            .on_envelope(None)
            .on_group_chat_converted_to_external_group(lambda event: seen.append(event))
        )

        dispatcher.dispatch(
            client,
            Envelope(
                cmd=COMMAND_EVENT,
                header=Header(app_id="app-1", callback_id="callback-1"),
                data={
                    "event_id": "external-group-event-1",
                    "event_type": EVENT_TYPE_GROUP_CHAT_CONVERTED_TO_EXTERNAL_GROUP,
                    "timestamp": 1611220944,
                    "app_id": "app-1",
                    "event": {
                        "group_id": "group-1",
                        "operator": {
                            "seatalk_id": "u-1",
                            "employee_code": "e_1",
                            "email": "sample@seatalk.biz",
                        },
                    },
                },
            ),
        )

        self.assertEqual(client.acks, ["callback-1"])
        self.assertEqual(len(seen), 1)
        event = seen[0]
        self.assertIsInstance(event, GroupChatConvertedToExternalGroupEvent)
        self.assertEqual(event.callback_id, "callback-1")
        self.assertEqual(event.event_id, "external-group-event-1")
        self.assertEqual(event.event_type, EVENT_TYPE_GROUP_CHAT_CONVERTED_TO_EXTERNAL_GROUP)
        self.assertEqual(event.timestamp, 1611220944)
        self.assertEqual(event.app_id, "app-1")
        self.assertEqual(event.event.group_id, "group-1")
        self.assertEqual(event.event.operator.seatalk_id, "u-1")
        self.assertEqual(event.event.operator.employee_code, "e_1")
        self.assertEqual(event.event.operator.email, "sample@seatalk.biz")

    def test_no_handler_no_ack(self) -> None:
        client = FakeClient()
        dispatcher = EventDispatcher().on_envelope(None)

        dispatcher.dispatch(
            client,
            Envelope(
                cmd=COMMAND_EVENT,
                header=Header(app_id="app-1", callback_id="callback-1"),
                data={"event_type": EVENT_TYPE_USER_ENTER_CHATROOM_WITH_BOT},
            ),
        )

        self.assertEqual(client.acks, [])

    def test_default_invalid_frame_handler_prints_and_continues(self) -> None:
        dispatcher = EventDispatcher().on_envelope(None)
        out = io.StringIO()
        with redirect_stdout(out):
            dispatcher.handle_invalid_frame(b"{bad", ValueError("bad json"))

        self.assertIn("non-json frame: {bad err: bad json", out.getvalue())

    def test_user_enter_parser(self) -> None:
        event = UserEnterChatroomWithBotEvent.from_data(
            {
                "event_id": "event-1",
                "event_type": EVENT_TYPE_USER_ENTER_CHATROOM_WITH_BOT,
                "timestamp": 1611220944,
                "app_id": "app-1",
                "event": {
                    "seatalk_id": "u-1",
                    "employee_code": "e_1",
                    "email": "sample@seatalk.biz",
                },
            },
            callback_id="callback-1",
        )

        self.assertEqual(event.callback_id, "callback-1")
        self.assertEqual(event.event.seatalk_id, "u-1")
        self.assertEqual(event.timestamp, 1611220944)


if __name__ == "__main__":
    unittest.main()
