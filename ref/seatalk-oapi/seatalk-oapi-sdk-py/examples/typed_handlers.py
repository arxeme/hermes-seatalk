#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seatalk_oapi_sdk import (
    MESSAGE_TAG_TEXT,
    Client,
    EventDispatcher,
    DEFAULT_WEB_SOCKET_URL,
    BotAddedToGroupChatEvent,
    BotRemovedFromGroupChatEvent,
    GroupChatConvertedToExternalGroupEvent,
    InteractiveMessageClickEvent,
    MessageFromBotSubscriberEvent,
    NewMentionedMessageReceivedFromGroupChatEvent,
    NewMessageReceivedFromThreadEvent,
    UserEnterChatroomWithBotEvent,
)


def handle_user_enter(event: UserEnterChatroomWithBotEvent) -> None:
    print("user entered chatroom:", event.event.seatalk_id, event.event.email)


def handle_subscriber_message(event: MessageFromBotSubscriberEvent) -> None:
    message = event.event.message
    if message.tag == MESSAGE_TAG_TEXT and message.text is not None:
        print("subscriber message:", message.text.content)


def handle_group_mention(event: NewMentionedMessageReceivedFromGroupChatEvent) -> None:
    message = event.event.message
    if message.text is not None:
        print("group mention:", event.event.group_id, message.text.plain_text)


def handle_interactive_click(event: InteractiveMessageClickEvent) -> None:
    print("interactive click:", event.event.message_id, event.event.value)


def handle_thread_message(event: NewMessageReceivedFromThreadEvent) -> None:
    message = event.event.message
    if message.text is not None:
        print("thread message:", message.thread_id, message.text.plain_text)


def handle_bot_added(event: BotAddedToGroupChatEvent) -> None:
    print("bot added:", event.event.group.group_id, event.event.group.group_name)


def handle_bot_removed(event: BotRemovedFromGroupChatEvent) -> None:
    print("bot removed:", event.event.group_id, event.event.remover.seatalk_id)


def handle_group_chat_converted(event: GroupChatConvertedToExternalGroupEvent) -> None:
    print("group converted to external:", event.event.group_id, event.event.operator.seatalk_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect to seatalk open platform with typed event handlers.")
    parser.add_argument("--url", default=DEFAULT_WEB_SOCKET_URL)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--app-secret", required=True)
    parser.add_argument("--log-level", default="DEBUG", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("seatalk_oapi_sdk_py")

    dispatcher = (
        EventDispatcher()
        .on_user_enter_chatroom_with_bot(handle_user_enter)
        .on_message_from_bot_subscriber(handle_subscriber_message)
        .on_new_mentioned_message_received_from_group_chat(handle_group_mention)
        .on_interactive_message_click(handle_interactive_click)
        .on_new_message_received_from_thread(handle_thread_message)
        .on_bot_added_to_group_chat(handle_bot_added)
        .on_bot_removed_from_group_chat(handle_bot_removed)
        .on_group_chat_converted_to_external_group(handle_group_chat_converted)
    )

    client = Client(args.app_id, args.app_secret, ws_url=args.url, dispatcher=dispatcher, logger=logger)
    try:
        client.run()
    except KeyboardInterrupt:
        print("shutting down")
    finally:
        client.close()


if __name__ == "__main__":
    main()
