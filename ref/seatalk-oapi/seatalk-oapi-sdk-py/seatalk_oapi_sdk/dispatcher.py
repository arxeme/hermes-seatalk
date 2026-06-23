from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .errors import KickError
from .protocol import (
    COMMAND_EVENT,
    COMMAND_KICK,
    COMMAND_PONG,
    EVENT_TYPE_BOT_ADDED_TO_GROUP_CHAT,
    EVENT_TYPE_BOT_REMOVED_FROM_GROUP_CHAT,
    EVENT_TYPE_GROUP_CHAT_CONVERTED_TO_EXTERNAL_GROUP,
    EVENT_TYPE_INTERACTIVE_MESSAGE_CLICK,
    EVENT_TYPE_MESSAGE_FROM_BOT_SUBSCRIBER,
    EVENT_TYPE_NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT,
    EVENT_TYPE_NEW_MESSAGE_RECEIVED_FROM_THREAD,
    EVENT_TYPE_USER_ENTER_CHATROOM_WITH_BOT,
    BotAddedToGroupChatEvent,
    BotRemovedFromGroupChatEvent,
    Envelope,
    Event,
    GroupChatConvertedToExternalGroupEvent,
    InteractiveMessageClickEvent,
    MessageFromBotSubscriberEvent,
    NewMentionedMessageReceivedFromGroupChatEvent,
    NewMessageReceivedFromThreadEvent,
    UserEnterChatroomWithBotEvent,
)

EventHandler = Callable[[Event], None]
EnvelopeHandler = Callable[[Envelope], None]
InvalidFrameHandler = Callable[[bytes, Exception], None]


class EventDispatcher:
    def __init__(self) -> None:
        self._on_event: Optional[EventHandler] = None
        self._on_user_enter_chatroom_with_bot: Optional[Callable[[UserEnterChatroomWithBotEvent], None]] = None
        self._on_message_from_bot_subscriber: Optional[Callable[[MessageFromBotSubscriberEvent], None]] = None
        self._on_new_mentioned_message_received_from_group_chat: Optional[
            Callable[[NewMentionedMessageReceivedFromGroupChatEvent], None]
        ] = None
        self._on_interactive_message_click: Optional[Callable[[InteractiveMessageClickEvent], None]] = None
        self._on_new_message_received_from_thread: Optional[Callable[[NewMessageReceivedFromThreadEvent], None]] = None
        self._on_bot_added_to_group_chat: Optional[Callable[[BotAddedToGroupChatEvent], None]] = None
        self._on_bot_removed_from_group_chat: Optional[Callable[[BotRemovedFromGroupChatEvent], None]] = None
        self._on_group_chat_converted_to_external_group: Optional[
            Callable[[GroupChatConvertedToExternalGroupEvent], None]
        ] = None
        self._on_kick: Optional[EnvelopeHandler] = None
        self._on_envelope: Optional[EnvelopeHandler] = default_envelope_handler
        self._on_invalid_frame: Optional[InvalidFrameHandler] = default_invalid_frame_handler

    def on_event(self, handler: Optional[EventHandler]) -> "EventDispatcher":
        self._on_event = handler
        return self

    def on_user_enter_chatroom_with_bot(
        self, handler: Optional[Callable[[UserEnterChatroomWithBotEvent], None]]
    ) -> "EventDispatcher":
        self._on_user_enter_chatroom_with_bot = handler
        return self

    def on_message_from_bot_subscriber(
        self, handler: Optional[Callable[[MessageFromBotSubscriberEvent], None]]
    ) -> "EventDispatcher":
        self._on_message_from_bot_subscriber = handler
        return self

    def on_new_mentioned_message_received_from_group_chat(
        self, handler: Optional[Callable[[NewMentionedMessageReceivedFromGroupChatEvent], None]]
    ) -> "EventDispatcher":
        self._on_new_mentioned_message_received_from_group_chat = handler
        return self

    def on_interactive_message_click(
        self, handler: Optional[Callable[[InteractiveMessageClickEvent], None]]
    ) -> "EventDispatcher":
        self._on_interactive_message_click = handler
        return self

    def on_new_message_received_from_thread(
        self, handler: Optional[Callable[[NewMessageReceivedFromThreadEvent], None]]
    ) -> "EventDispatcher":
        self._on_new_message_received_from_thread = handler
        return self

    def on_bot_added_to_group_chat(self, handler: Optional[Callable[[BotAddedToGroupChatEvent], None]]) -> "EventDispatcher":
        self._on_bot_added_to_group_chat = handler
        return self

    def on_bot_removed_from_group_chat(
        self, handler: Optional[Callable[[BotRemovedFromGroupChatEvent], None]]
    ) -> "EventDispatcher":
        self._on_bot_removed_from_group_chat = handler
        return self

    def on_group_chat_converted_to_external_group(
        self, handler: Optional[Callable[[GroupChatConvertedToExternalGroupEvent], None]]
    ) -> "EventDispatcher":
        self._on_group_chat_converted_to_external_group = handler
        return self

    def on_kick(self, handler: Optional[EnvelopeHandler]) -> "EventDispatcher":
        self._on_kick = handler
        return self

    def on_envelope(self, handler: Optional[EnvelopeHandler]) -> "EventDispatcher":
        self._on_envelope = handler
        return self

    def on_invalid_frame(self, handler: Optional[InvalidFrameHandler]) -> "EventDispatcher":
        self._on_invalid_frame = handler
        return self

    def dispatch(self, client: Any, envelope: Envelope) -> None:
        if envelope.cmd == COMMAND_PONG:
            return

        if self._on_envelope is not None:
            self._on_envelope(envelope)

        if envelope.cmd == COMMAND_EVENT:
            event = Event(
                app_id=envelope.header.app_id,
                callback_id=envelope.header.callback_id,
                data=envelope.data,
                rid=envelope.header.rid,
                sid=envelope.header.sid,
            )
            handled = False
            if self._on_event is not None:
                self._on_event(event)
                handled = True

            handled = self._dispatch_typed_event(event) or handled
            if handled and event.callback_id:
                client.ack(event.callback_id)
            return

        if envelope.cmd == COMMAND_KICK:
            if self._on_kick is not None:
                self._on_kick(envelope)
            raise KickError(envelope.message, envelope)

    def handle_invalid_frame(self, payload: bytes, err: Exception) -> None:
        if self._on_invalid_frame is not None:
            self._on_invalid_frame(payload, err)
            return
        raise err

    def _dispatch_typed_event(self, event: Event) -> bool:
        if not self._has_typed_event_handler():
            return False

        data = event.data if isinstance(event.data, dict) else {}
        event_type = data.get("event_type", "")

        if event_type == EVENT_TYPE_USER_ENTER_CHATROOM_WITH_BOT:
            if self._on_user_enter_chatroom_with_bot is None:
                return False
            self._on_user_enter_chatroom_with_bot(UserEnterChatroomWithBotEvent.from_data(data, event.callback_id))
            return True

        if event_type == EVENT_TYPE_MESSAGE_FROM_BOT_SUBSCRIBER:
            if self._on_message_from_bot_subscriber is None:
                return False
            self._on_message_from_bot_subscriber(MessageFromBotSubscriberEvent.from_data(data, event.callback_id))
            return True

        if event_type == EVENT_TYPE_NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT:
            if self._on_new_mentioned_message_received_from_group_chat is None:
                return False
            self._on_new_mentioned_message_received_from_group_chat(
                NewMentionedMessageReceivedFromGroupChatEvent.from_data(data, event.callback_id)
            )
            return True

        if event_type == EVENT_TYPE_INTERACTIVE_MESSAGE_CLICK:
            if self._on_interactive_message_click is None:
                return False
            self._on_interactive_message_click(InteractiveMessageClickEvent.from_data(data, event.callback_id))
            return True

        if event_type == EVENT_TYPE_NEW_MESSAGE_RECEIVED_FROM_THREAD:
            if self._on_new_message_received_from_thread is None:
                return False
            self._on_new_message_received_from_thread(NewMessageReceivedFromThreadEvent.from_data(data, event.callback_id))
            return True

        if event_type == EVENT_TYPE_BOT_ADDED_TO_GROUP_CHAT:
            if self._on_bot_added_to_group_chat is None:
                return False
            self._on_bot_added_to_group_chat(BotAddedToGroupChatEvent.from_data(data, event.callback_id))
            return True

        if event_type == EVENT_TYPE_BOT_REMOVED_FROM_GROUP_CHAT:
            if self._on_bot_removed_from_group_chat is None:
                return False
            self._on_bot_removed_from_group_chat(BotRemovedFromGroupChatEvent.from_data(data, event.callback_id))
            return True

        if event_type == EVENT_TYPE_GROUP_CHAT_CONVERTED_TO_EXTERNAL_GROUP:
            if self._on_group_chat_converted_to_external_group is None:
                return False
            self._on_group_chat_converted_to_external_group(
                GroupChatConvertedToExternalGroupEvent.from_data(data, event.callback_id)
            )
            return True

        return False

    def _has_typed_event_handler(self) -> bool:
        return any(
            [
                self._on_user_enter_chatroom_with_bot,
                self._on_message_from_bot_subscriber,
                self._on_new_mentioned_message_received_from_group_chat,
                self._on_interactive_message_click,
                self._on_new_message_received_from_thread,
                self._on_bot_added_to_group_chat,
                self._on_bot_removed_from_group_chat,
                self._on_group_chat_converted_to_external_group,
            ]
        )

    def OnEvent(self, handler: Optional[EventHandler]) -> "EventDispatcher":
        return self.on_event(handler)

    def OnUserEnterChatroomWithBot(
        self, handler: Optional[Callable[[UserEnterChatroomWithBotEvent], None]]
    ) -> "EventDispatcher":
        return self.on_user_enter_chatroom_with_bot(handler)

    def OnMessageFromBotSubscriber(
        self, handler: Optional[Callable[[MessageFromBotSubscriberEvent], None]]
    ) -> "EventDispatcher":
        return self.on_message_from_bot_subscriber(handler)

    def OnNewMentionedMessageReceivedFromGroupChat(
        self, handler: Optional[Callable[[NewMentionedMessageReceivedFromGroupChatEvent], None]]
    ) -> "EventDispatcher":
        return self.on_new_mentioned_message_received_from_group_chat(handler)

    def OnInteractiveMessageClick(
        self, handler: Optional[Callable[[InteractiveMessageClickEvent], None]]
    ) -> "EventDispatcher":
        return self.on_interactive_message_click(handler)

    def OnNewMessageReceivedFromThread(
        self, handler: Optional[Callable[[NewMessageReceivedFromThreadEvent], None]]
    ) -> "EventDispatcher":
        return self.on_new_message_received_from_thread(handler)

    def OnBotAddedToGroupChat(self, handler: Optional[Callable[[BotAddedToGroupChatEvent], None]]) -> "EventDispatcher":
        return self.on_bot_added_to_group_chat(handler)

    def OnBotRemovedFromGroupChat(
        self, handler: Optional[Callable[[BotRemovedFromGroupChatEvent], None]]
    ) -> "EventDispatcher":
        return self.on_bot_removed_from_group_chat(handler)

    def OnGroupChatConvertedToExternalGroup(
        self, handler: Optional[Callable[[GroupChatConvertedToExternalGroupEvent], None]]
    ) -> "EventDispatcher":
        return self.on_group_chat_converted_to_external_group(handler)

    def OnKick(self, handler: Optional[EnvelopeHandler]) -> "EventDispatcher":
        return self.on_kick(handler)

    def OnEnvelope(self, handler: Optional[EnvelopeHandler]) -> "EventDispatcher":
        return self.on_envelope(handler)

    def OnInvalidFrame(self, handler: Optional[InvalidFrameHandler]) -> "EventDispatcher":
        return self.on_invalid_frame(handler)


def default_envelope_handler(envelope: Envelope) -> None:
    print(json.dumps(envelope.to_dict(), ensure_ascii=False, indent=2))


def default_invalid_frame_handler(payload: bytes, err: Exception) -> None:
    text = payload.decode("utf-8", errors="replace")
    print("non-json frame: %s err: %s" % (text, err))
