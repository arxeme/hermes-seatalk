from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


DEFAULT_WEB_SOCKET_URL = "wss://ws-openapi.haiserve.com/ws/bot"

COMMAND_REGISTER = "register"
COMMAND_ACK = "ack"
COMMAND_PING = "ping"
COMMAND_PONG = "pong"
COMMAND_KICK = "kick"
COMMAND_EVENT = "event"

EVENT_TYPE_USER_ENTER_CHATROOM_WITH_BOT = "user_enter_chatroom_with_bot"
EVENT_TYPE_MESSAGE_FROM_BOT_SUBSCRIBER = "message_from_bot_subscriber"
EVENT_TYPE_NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT = "new_mentioned_message_received_from_group_chat"
EVENT_TYPE_INTERACTIVE_MESSAGE_CLICK = "interactive_message_click"
EVENT_TYPE_NEW_MESSAGE_RECEIVED_FROM_THREAD = "new_message_received_from_thread"
EVENT_TYPE_BOT_ADDED_TO_GROUP_CHAT = "bot_added_to_group_chat"
EVENT_TYPE_BOT_REMOVED_FROM_GROUP_CHAT = "bot_removed_from_group_chat"
EVENT_TYPE_GROUP_CHAT_CONVERTED_TO_EXTERNAL_GROUP = "group_chat_converted_to_external_group"

MESSAGE_TAG_TEXT = "text"
MESSAGE_TAG_COMBINED_FORWARDED_CHAT_HISTORY = "combined_forwarded_chat_history"
MESSAGE_TAG_IMAGE = "image"
MESSAGE_TAG_FILE = "file"
MESSAGE_TAG_VIDEO = "video"

CODE_OK = 0
CODE_ERROR = 1


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _string(data: Dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    return "" if value is None else str(value)


def _uint(data: Dict[str, Any], key: str) -> int:
    value = data.get(key, 0)
    if value in ("", None):
        return 0
    return int(value)


@dataclass
class Header:
    app_id: str = ""
    app_secret: str = ""
    token: str = ""
    sid: str = ""
    callback_id: str = ""
    rid: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "Header":
        data = _as_dict(data)
        return cls(
            app_id=_string(data, "app_id"),
            app_secret=_string(data, "app_secret"),
            token=_string(data, "token"),
            sid=_string(data, "sid"),
            callback_id=_string(data, "callback_id"),
            rid=_string(data, "rid"),
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.app_id:
            out["app_id"] = self.app_id
        if self.app_secret:
            out["app_secret"] = self.app_secret
        if self.token:
            out["token"] = self.token
        if self.sid:
            out["sid"] = self.sid
        if self.callback_id:
            out["callback_id"] = self.callback_id
        if self.rid:
            out["rid"] = self.rid
        return out


@dataclass
class Envelope:
    cmd: str
    header: Header = field(default_factory=Header)
    data: Any = None
    code: int = 0
    message: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "Envelope":
        data = _as_dict(data)
        return cls(
            cmd=_string(data, "cmd"),
            header=Header.from_dict(data.get("header")),
            data=data.get("data"),
            code=int(data.get("code", 0) or 0),
            message=_string(data, "message"),
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"cmd": self.cmd}
        header = self.header.to_dict()
        if header:
            out["header"] = header
        if self.data is not None:
            out["data"] = self.data
        if self.code:
            out["code"] = self.code
        if self.message:
            out["message"] = self.message
        return out


@dataclass
class RegisterResult:
    app_id: str
    token: str
    sid: str = ""
    heartbeat_interval: float = 0.0
    heartbeat_timeout: float = 0.0


@dataclass
class RegisterSettings:
    heartbeat_interval: int = 0
    heartbeat_timeout: int = 0

    @classmethod
    def from_dict(cls, data: Any) -> "RegisterSettings":
        data = _as_dict(data)
        return cls(
            heartbeat_interval=_uint(data, "heartbeat_interval"),
            heartbeat_timeout=_uint(data, "heartbeat_timeout"),
        )


@dataclass
class Event:
    app_id: str
    callback_id: str
    data: Any
    rid: str = ""
    sid: str = ""


@dataclass
class UserEnterChatroomWithBotEventDetail:
    employee_code: str = ""
    seatalk_id: str = ""
    email: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "UserEnterChatroomWithBotEventDetail":
        data = _as_dict(data)
        return cls(
            employee_code=_string(data, "employee_code"),
            seatalk_id=_string(data, "seatalk_id"),
            email=_string(data, "email"),
        )


@dataclass
class UserEnterChatroomWithBotEvent:
    callback_id: str
    event_id: str
    event_type: str
    timestamp: int
    app_id: str
    event: UserEnterChatroomWithBotEventDetail

    @classmethod
    def from_data(cls, data: Any, callback_id: str = "") -> "UserEnterChatroomWithBotEvent":
        data = _as_dict(data)
        return cls(
            callback_id=callback_id,
            event_id=_string(data, "event_id"),
            event_type=_string(data, "event_type"),
            timestamp=_uint(data, "timestamp"),
            app_id=_string(data, "app_id"),
            event=UserEnterChatroomWithBotEventDetail.from_dict(data.get("event")),
        )


@dataclass
class TextMessage:
    content: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> Optional["TextMessage"]:
        if data is None:
            return None
        data = _as_dict(data)
        return cls(content=_string(data, "content"))


@dataclass
class MediaMessage:
    content: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> Optional["MediaMessage"]:
        if data is None:
            return None
        data = _as_dict(data)
        return cls(content=_string(data, "content"))


@dataclass
class FileMessage:
    content: str = ""
    filename: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> Optional["FileMessage"]:
        if data is None:
            return None
        data = _as_dict(data)
        return cls(content=_string(data, "content"), filename=_string(data, "filename"))


@dataclass
class BotSubscriberMessage:
    message_id: str = ""
    quoted_message_id: str = ""
    thread_id: str = ""
    tag: str = ""
    text: Optional[TextMessage] = None
    image: Optional[MediaMessage] = None
    file: Optional[FileMessage] = None
    video: Optional[MediaMessage] = None

    @classmethod
    def from_dict(cls, data: Any) -> "BotSubscriberMessage":
        data = _as_dict(data)
        return cls(
            message_id=_string(data, "message_id"),
            quoted_message_id=_string(data, "quoted_message_id"),
            thread_id=_string(data, "thread_id"),
            tag=_string(data, "tag"),
            text=TextMessage.from_dict(data.get("text")),
            image=MediaMessage.from_dict(data.get("image")),
            file=FileMessage.from_dict(data.get("file")),
            video=MediaMessage.from_dict(data.get("video")),
        )


@dataclass
class MessageFromBotSubscriberEventDetail:
    seatalk_id: str = ""
    employee_code: str = ""
    email: str = ""
    message: BotSubscriberMessage = field(default_factory=BotSubscriberMessage)

    @classmethod
    def from_dict(cls, data: Any) -> "MessageFromBotSubscriberEventDetail":
        data = _as_dict(data)
        return cls(
            seatalk_id=_string(data, "seatalk_id"),
            employee_code=_string(data, "employee_code"),
            email=_string(data, "email"),
            message=BotSubscriberMessage.from_dict(data.get("message")),
        )


@dataclass
class MessageFromBotSubscriberEvent:
    callback_id: str
    event_id: str
    event_type: str
    timestamp: int
    app_id: str
    event: MessageFromBotSubscriberEventDetail

    @classmethod
    def from_data(cls, data: Any, callback_id: str = "") -> "MessageFromBotSubscriberEvent":
        data = _as_dict(data)
        return cls(
            callback_id=callback_id,
            event_id=_string(data, "event_id"),
            event_type=_string(data, "event_type"),
            timestamp=_uint(data, "timestamp"),
            app_id=_string(data, "app_id"),
            event=MessageFromBotSubscriberEventDetail.from_dict(data.get("event")),
        )


@dataclass
class MentionedGroupChatActor:
    username: str = ""
    seatalk_id: str = ""
    employee_code: str = ""
    email: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "MentionedGroupChatActor":
        data = _as_dict(data)
        return cls(
            username=_string(data, "username"),
            seatalk_id=_string(data, "seatalk_id"),
            employee_code=_string(data, "employee_code"),
            email=_string(data, "email"),
        )


@dataclass
class MentionedGroupChatText:
    plain_text: str = ""
    mentioned_list: List[MentionedGroupChatActor] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Any) -> Optional["MentionedGroupChatText"]:
        if data is None:
            return None
        data = _as_dict(data)
        return cls(
            plain_text=_string(data, "plain_text"),
            mentioned_list=[MentionedGroupChatActor.from_dict(x) for x in _as_list(data.get("mentioned_list"))],
        )


@dataclass
class MentionedGroupChatSender:
    seatalk_id: str = ""
    employee_code: str = ""
    email: str = ""
    sender_type: int = 0

    @classmethod
    def from_dict(cls, data: Any) -> "MentionedGroupChatSender":
        data = _as_dict(data)
        return cls(
            seatalk_id=_string(data, "seatalk_id"),
            employee_code=_string(data, "employee_code"),
            email=_string(data, "email"),
            sender_type=int(data.get("sender_type", 0) or 0),
        )


@dataclass
class MentionedGroupChatMessage:
    message_id: str = ""
    quoted_message_id: str = ""
    thread_id: str = ""
    sender: MentionedGroupChatSender = field(default_factory=MentionedGroupChatSender)
    message_sent_time: int = 0
    tag: str = ""
    text: Optional[MentionedGroupChatText] = None

    @classmethod
    def from_dict(cls, data: Any) -> "MentionedGroupChatMessage":
        data = _as_dict(data)
        return cls(
            message_id=_string(data, "message_id"),
            quoted_message_id=_string(data, "quoted_message_id"),
            thread_id=_string(data, "thread_id"),
            sender=MentionedGroupChatSender.from_dict(data.get("sender")),
            message_sent_time=_uint(data, "message_sent_time"),
            tag=_string(data, "tag"),
            text=MentionedGroupChatText.from_dict(data.get("text")),
        )


@dataclass
class NewMentionedMessageReceivedFromGroupChatEventData:
    group_id: str = ""
    message: MentionedGroupChatMessage = field(default_factory=MentionedGroupChatMessage)

    @classmethod
    def from_dict(cls, data: Any) -> "NewMentionedMessageReceivedFromGroupChatEventData":
        data = _as_dict(data)
        return cls(
            group_id=_string(data, "group_id"),
            message=MentionedGroupChatMessage.from_dict(data.get("message")),
        )


@dataclass
class NewMentionedMessageReceivedFromGroupChatEvent:
    callback_id: str
    event_id: str
    event_type: str
    timestamp: int
    app_id: str
    event: NewMentionedMessageReceivedFromGroupChatEventData

    @classmethod
    def from_data(cls, data: Any, callback_id: str = "") -> "NewMentionedMessageReceivedFromGroupChatEvent":
        data = _as_dict(data)
        return cls(
            callback_id=callback_id,
            event_id=_string(data, "event_id"),
            event_type=_string(data, "event_type"),
            timestamp=_uint(data, "timestamp"),
            app_id=_string(data, "app_id"),
            event=NewMentionedMessageReceivedFromGroupChatEventData.from_dict(data.get("event")),
        )


@dataclass
class InteractiveMessageClickEventDetail:
    message_id: str = ""
    employee_code: str = ""
    email: str = ""
    value: str = ""
    seatalk_id: str = ""
    group_id: str = ""
    thread_id: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "InteractiveMessageClickEventDetail":
        data = _as_dict(data)
        return cls(
            message_id=_string(data, "message_id"),
            employee_code=_string(data, "employee_code"),
            email=_string(data, "email"),
            value=_string(data, "value"),
            seatalk_id=_string(data, "seatalk_id"),
            group_id=_string(data, "group_id"),
            thread_id=_string(data, "thread_id"),
        )


@dataclass
class InteractiveMessageClickEvent:
    callback_id: str
    event_id: str
    event_type: str
    timestamp: int
    app_id: str
    event: InteractiveMessageClickEventDetail

    @classmethod
    def from_data(cls, data: Any, callback_id: str = "") -> "InteractiveMessageClickEvent":
        data = _as_dict(data)
        return cls(
            callback_id=callback_id,
            event_id=_string(data, "event_id"),
            event_type=_string(data, "event_type"),
            timestamp=_uint(data, "timestamp"),
            app_id=_string(data, "app_id"),
            event=InteractiveMessageClickEventDetail.from_dict(data.get("event")),
        )


@dataclass
class ThreadMentionedActor:
    username: str = ""
    seatalk_id: str = ""
    employee_code: str = ""
    email: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "ThreadMentionedActor":
        data = _as_dict(data)
        return cls(
            username=_string(data, "username"),
            seatalk_id=_string(data, "seatalk_id"),
            employee_code=_string(data, "employee_code"),
            email=_string(data, "email"),
        )


@dataclass
class ThreadTextMessage:
    plain_text: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> Optional["ThreadTextMessage"]:
        if data is None:
            return None
        data = _as_dict(data)
        return cls(plain_text=_string(data, "plain_text"))


@dataclass
class ThreadMessageSender:
    seatalk_id: str = ""
    employee_code: str = ""
    email: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "ThreadMessageSender":
        data = _as_dict(data)
        return cls(
            seatalk_id=_string(data, "seatalk_id"),
            employee_code=_string(data, "employee_code"),
            email=_string(data, "email"),
        )


@dataclass
class ThreadMessage:
    message_id: str = ""
    quoted_message_id: str = ""
    thread_id: str = ""
    sender: ThreadMessageSender = field(default_factory=ThreadMessageSender)
    message_sent_time: int = 0
    tag: str = ""
    text: Optional[ThreadTextMessage] = None
    image: Optional[MediaMessage] = None
    file: Optional[FileMessage] = None
    video: Optional[MediaMessage] = None
    mentioned_list: List[ThreadMentionedActor] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Any) -> "ThreadMessage":
        data = _as_dict(data)
        return cls(
            message_id=_string(data, "message_id"),
            quoted_message_id=_string(data, "quoted_message_id"),
            thread_id=_string(data, "thread_id"),
            sender=ThreadMessageSender.from_dict(data.get("sender")),
            message_sent_time=_uint(data, "message_sent_time"),
            tag=_string(data, "tag"),
            text=ThreadTextMessage.from_dict(data.get("text")),
            image=MediaMessage.from_dict(data.get("image")),
            file=FileMessage.from_dict(data.get("file")),
            video=MediaMessage.from_dict(data.get("video")),
            mentioned_list=[ThreadMentionedActor.from_dict(x) for x in _as_list(data.get("mentioned_list"))],
        )


@dataclass
class NewMessageReceivedFromThreadEventData:
    group_id: str = ""
    message: ThreadMessage = field(default_factory=ThreadMessage)

    @classmethod
    def from_dict(cls, data: Any) -> "NewMessageReceivedFromThreadEventData":
        data = _as_dict(data)
        return cls(
            group_id=_string(data, "group_id"),
            message=ThreadMessage.from_dict(data.get("message")),
        )


@dataclass
class NewMessageReceivedFromThreadEvent:
    callback_id: str
    event_id: str
    event_type: str
    timestamp: int
    app_id: str
    event: NewMessageReceivedFromThreadEventData

    @classmethod
    def from_data(cls, data: Any, callback_id: str = "") -> "NewMessageReceivedFromThreadEvent":
        data = _as_dict(data)
        return cls(
            callback_id=callback_id,
            event_id=_string(data, "event_id"),
            event_type=_string(data, "event_type"),
            timestamp=_uint(data, "timestamp"),
            app_id=_string(data, "app_id"),
            event=NewMessageReceivedFromThreadEventData.from_dict(data.get("event")),
        )


@dataclass
class BotAddedGroupSettings:
    chat_history_for_new_members: str = ""
    can_notify_with_at_all: bool = False
    can_view_member_list: bool = False

    @classmethod
    def from_dict(cls, data: Any) -> "BotAddedGroupSettings":
        data = _as_dict(data)
        return cls(
            chat_history_for_new_members=_string(data, "chat_history_for_new_members"),
            can_notify_with_at_all=bool(data.get("can_notify_with_at_all", False)),
            can_view_member_list=bool(data.get("can_view_member_list", False)),
        )


@dataclass
class BotAddedGroupChat:
    group_id: str = ""
    group_name: str = ""
    group_settings: BotAddedGroupSettings = field(default_factory=BotAddedGroupSettings)

    @classmethod
    def from_dict(cls, data: Any) -> "BotAddedGroupChat":
        data = _as_dict(data)
        return cls(
            group_id=_string(data, "group_id"),
            group_name=_string(data, "group_name"),
            group_settings=BotAddedGroupSettings.from_dict(data.get("group_settings")),
        )


@dataclass
class BotAddedInviter:
    seatalk_id: str = ""
    employee_code: str = ""
    email: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "BotAddedInviter":
        data = _as_dict(data)
        return cls(
            seatalk_id=_string(data, "seatalk_id"),
            employee_code=_string(data, "employee_code"),
            email=_string(data, "email"),
        )


@dataclass
class BotAddedToGroupChatEventData:
    group: BotAddedGroupChat = field(default_factory=BotAddedGroupChat)
    inviter: BotAddedInviter = field(default_factory=BotAddedInviter)

    @classmethod
    def from_dict(cls, data: Any) -> "BotAddedToGroupChatEventData":
        data = _as_dict(data)
        return cls(
            group=BotAddedGroupChat.from_dict(data.get("group")),
            inviter=BotAddedInviter.from_dict(data.get("inviter")),
        )


@dataclass
class BotAddedToGroupChatEvent:
    callback_id: str
    event_id: str
    event_type: str
    timestamp: int
    app_id: str
    event: BotAddedToGroupChatEventData

    @classmethod
    def from_data(cls, data: Any, callback_id: str = "") -> "BotAddedToGroupChatEvent":
        data = _as_dict(data)
        return cls(
            callback_id=callback_id,
            event_id=_string(data, "event_id"),
            event_type=_string(data, "event_type"),
            timestamp=_uint(data, "timestamp"),
            app_id=_string(data, "app_id"),
            event=BotAddedToGroupChatEventData.from_dict(data.get("event")),
        )


@dataclass
class BotRemovedRemover:
    seatalk_id: str = ""
    employee_code: str = ""
    email: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "BotRemovedRemover":
        data = _as_dict(data)
        return cls(
            seatalk_id=_string(data, "seatalk_id"),
            employee_code=_string(data, "employee_code"),
            email=_string(data, "email"),
        )


@dataclass
class BotRemovedFromGroupChatDetails:
    group_id: str = ""
    remover: BotRemovedRemover = field(default_factory=BotRemovedRemover)

    @classmethod
    def from_dict(cls, data: Any) -> "BotRemovedFromGroupChatDetails":
        data = _as_dict(data)
        return cls(
            group_id=_string(data, "group_id"),
            remover=BotRemovedRemover.from_dict(data.get("remover")),
        )


@dataclass
class BotRemovedFromGroupChatEvent:
    callback_id: str
    event_id: str
    event_type: str
    timestamp: int
    app_id: str
    event: BotRemovedFromGroupChatDetails

    @classmethod
    def from_data(cls, data: Any, callback_id: str = "") -> "BotRemovedFromGroupChatEvent":
        data = _as_dict(data)
        return cls(
            callback_id=callback_id,
            event_id=_string(data, "event_id"),
            event_type=_string(data, "event_type"),
            timestamp=_uint(data, "timestamp"),
            app_id=_string(data, "app_id"),
            event=BotRemovedFromGroupChatDetails.from_dict(data.get("event")),
        )


@dataclass
class GroupChatConvertedToExternalGroupOperator:
    seatalk_id: str = ""
    employee_code: str = ""
    email: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "GroupChatConvertedToExternalGroupOperator":
        data = _as_dict(data)
        return cls(
            seatalk_id=_string(data, "seatalk_id"),
            employee_code=_string(data, "employee_code"),
            email=_string(data, "email"),
        )


@dataclass
class GroupChatConvertedToExternalGroupEventData:
    group_id: str = ""
    operator: GroupChatConvertedToExternalGroupOperator = field(
        default_factory=GroupChatConvertedToExternalGroupOperator
    )

    @classmethod
    def from_dict(cls, data: Any) -> "GroupChatConvertedToExternalGroupEventData":
        data = _as_dict(data)
        return cls(
            group_id=_string(data, "group_id"),
            operator=GroupChatConvertedToExternalGroupOperator.from_dict(data.get("operator")),
        )


@dataclass
class GroupChatConvertedToExternalGroupEvent:
    callback_id: str
    event_id: str
    event_type: str
    timestamp: int
    app_id: str
    event: GroupChatConvertedToExternalGroupEventData

    @classmethod
    def from_data(cls, data: Any, callback_id: str = "") -> "GroupChatConvertedToExternalGroupEvent":
        data = _as_dict(data)
        return cls(
            callback_id=callback_id,
            event_id=_string(data, "event_id"),
            event_type=_string(data, "event_type"),
            timestamp=_uint(data, "timestamp"),
            app_id=_string(data, "app_id"),
            event=GroupChatConvertedToExternalGroupEventData.from_dict(data.get("event")),
        )
