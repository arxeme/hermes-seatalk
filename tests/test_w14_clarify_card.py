from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from hermes_seatalk import adapter, clarify_card
from hermes_seatalk.dispatcher import SeaTalkEventDispatcher

CID = "0123456789"


class FakeClarifyClient:
    def __init__(self, *, fetched=None, update_error=None, card_send_error=None):
        self.sent = []
        self.updates = []
        self._fetched = fetched
        self._update_error = update_error
        self._card_send_error = card_send_error

    def _fail(self, message):
        if self._card_send_error is not None and message.get("tag") == "interactive_message":
            raise self._card_send_error

    async def send_single_chat(self, employee_code, message, thread_id=None):
        self._fail(message)
        self.sent.append(("single", employee_code, message, thread_id))
        return {"code": 0, "message_id": "card-1"}

    async def send_group_chat(self, group_id, message, thread_id=None):
        self._fail(message)
        self.sent.append(("group", group_id, message, thread_id))
        return {"code": 0, "message_id": "card-1"}

    async def get_message_by_id(self, message_id):
        if self._fetched is not None:
            return self._fetched
        return {
            "code": 0,
            "interactive_message": {
                "last_edited_time": 0,
                "elements": self.sent[0][2]["interactive_message"]["elements"],
            },
        }

    async def update_message(self, message_id, message):
        if self._update_error is not None:
            raise self._update_error
        self.updates.append((message_id, message))
        return {"code": 0}

    async def get_employee_code_by_email(self, emails):
        return {email: None for email in emails}

    async def close(self):
        return None


def _account(app_id):
    return {
        "app_id": app_id,
        "app_secret": "app-secret",
        "signing_secret": "signing-secret",
        "mode": "webhook",
        "outbound_coalescing": False,
    }


def _config(client, second=None):
    accounts = {"default": _account("app-id")}
    clients = {"default": client}
    if second is not None:
        accounts["second"] = _account("app-second")
        clients["second"] = second
    return SimpleNamespace(
        extra={"accounts": accounts, "clients": clients},
        enabled=True,
    )


def _card(chat_id="group/G1", *, message_id="card-1", thread_id=None, account_id="default"):
    return clarify_card.SeaTalkClarifyCard(message_id, chat_id, thread_id, account_id)


async def _sent_card(client, chat_id="group/G1", choices=("Yes", "No")):
    seatalk = adapter.SeaTalkAdapter(_config(client))
    await seatalk.send_clarify(chat_id, "Proceed?", list(choices), CID, "sess")
    return seatalk


def _closed_text(client, index=0):
    return client.updates[index][1]["interactive_message"]["elements"][-1]["description"]["text"]


@pytest.fixture
def fake_clarify(monkeypatch):
    import threading

    entry = SimpleNamespace(choices=["Yes", "No", "Again"], multi_select=False)
    state = SimpleNamespace(resolved=[], awaited=[], resolve_ok=True, await_ok=True)

    def resolve_gateway_clarify(clarify_id, response):
        state.resolved.append((clarify_id, response))
        return state.resolve_ok

    def mark_awaiting_text(clarify_id):
        state.awaited.append(clarify_id)
        return state.await_ok

    module = SimpleNamespace(
        _lock=threading.Lock(),
        _entries={CID: entry},
        resolve_gateway_clarify=resolve_gateway_clarify,
        mark_awaiting_text=mark_awaiting_text,
    )
    state.module = module
    state.entry = entry
    monkeypatch.setitem(sys.modules, "tools", SimpleNamespace(clarify_gateway=module))
    monkeypatch.setitem(sys.modules, "tools.clarify_gateway", module)
    return state


def test_t14_01_choice_value_round_trip():
    value = clarify_card.encode_clarify_choice_value(CID, 2)
    assert value == f"stc1:{CID}:2"
    assert clarify_card.decode_clarify_value(value) == (CID, 2)


def test_t14_02_other_value_round_trip():
    value = clarify_card.encode_clarify_other_value(CID)
    assert value == f"stco1:{CID}"
    assert clarify_card.decode_clarify_value(value) == (CID, None)


def test_t14_03_foreign_or_malformed_value_is_ignored():
    assert clarify_card.decode_clarify_value("stq1:ask_x:0") is None
    assert clarify_card.decode_clarify_value(f"stc1:{CID}:4") is None
    assert clarify_card.decode_clarify_value("stc1:NOTHEX0000:1") is None
    assert clarify_card.decode_clarify_value(f"stc1:{CID}") is None
    assert clarify_card.decode_clarify_value(None) is None


def test_t14_04_malformed_clarify_id_is_refused():
    assert clarify_card.encode_clarify_choice_value("zz", 0) is None
    assert clarify_card.encode_clarify_other_value("zz") is None


def test_t14_05_card_has_one_button_per_choice_plus_other():
    elements = clarify_card.build_clarify_elements(
        question="Proceed?", choices=["Yes", "No", "Again"], clarify_id=CID
    )
    assert elements is not None
    labels = [e["button"]["text"] for e in elements if e["element_type"] == "button"]
    assert labels == ["Yes", "No", "Again", clarify_card.CLARIFY_OTHER_LABEL]
    assert elements[0] == {
        "element_type": "description",
        "description": {"format": 1, "text": "Proceed?"},
    }
    assert len([e for e in elements if e["element_type"] == "description"]) == 1


def test_t14_08_card_refused_for_unrenderable_input():
    assert clarify_card.build_clarify_elements(question="", choices=["a"], clarify_id=CID) is None
    assert (
        clarify_card.build_clarify_elements(question="x" * 1001, choices=["a"], clarify_id=CID)
        is None
    )
    assert (
        clarify_card.build_clarify_elements(
            question="Proceed?", choices=["a", "b", "c", "d", "e"], clarify_id=CID
        )
        is None
    )


def test_t14_09_closed_card_ticks_the_chosen_option():
    elements = clarify_card.build_clarify_elements(
        question="Proceed?", choices=["Yes", "No"], clarify_id=CID
    )
    closed = clarify_card.build_closed_clarify_elements(elements, 1, None)
    assert closed is not None
    assert not any(e["element_type"].startswith("button") for e in closed)
    text = closed[-1]["description"]["text"]
    assert text.startswith(clarify_card.CLOSED_DIVIDER)
    assert f"{clarify_card.CHOSEN_OPTION} No" in text
    assert f"{clarify_card.UNCHOSEN_OPTION} Yes" in text
    assert f"{clarify_card.UNCHOSEN_OPTION} {clarify_card.CLARIFY_OTHER_LABEL}" in text


def test_t14_09b_closed_card_ticks_other_by_position():
    elements = clarify_card.build_clarify_elements(
        question="Proceed?", choices=[clarify_card.CLARIFY_OTHER_LABEL, "No"], clarify_id=CID
    )
    text = clarify_card.build_closed_clarify_elements(
        elements, clarify_card.CLARIFY_OTHER_INDEX, "Reply"
    )[-1]["description"]["text"]
    assert text.count(clarify_card.CHOSEN_OPTION) == 1
    assert text.endswith(f"{clarify_card.CHOSEN_OPTION} {clarify_card.CLARIFY_OTHER_LABEL}\n\n_Reply_")


def test_t14_10_closed_card_without_a_tick_shows_the_status():
    elements = clarify_card.build_clarify_elements(
        question="Proceed?", choices=["Yes", "No"], clarify_id=CID
    )
    text = clarify_card.build_closed_clarify_elements(elements, None, "Expired")[-1]["description"][
        "text"
    ]
    assert text == f"{clarify_card.CLOSED_DIVIDER}\n_Expired_"


@pytest.mark.asyncio
async def test_t14_11_open_ended_falls_back_to_text(fake_clarify):
    client = FakeClarifyClient()
    seatalk = adapter.SeaTalkAdapter(_config(client))

    await seatalk.send_clarify("EmpOne", "What next?", None, CID, "sess")

    assert client.sent[0][2]["tag"] == "text"


@pytest.mark.asyncio
async def test_t14_12_multi_select_falls_back_to_text(fake_clarify):
    fake_clarify.entry.multi_select = True
    client = FakeClarifyClient()
    seatalk = adapter.SeaTalkAdapter(_config(client))

    await seatalk.send_clarify("EmpOne", "Pick some", ["a", "b"], CID, "sess")

    assert client.sent[0][2]["tag"] == "text"


@pytest.mark.asyncio
async def test_t14_13_single_select_sends_a_card(fake_clarify):
    client = FakeClarifyClient()
    seatalk = adapter.SeaTalkAdapter(_config(client))

    result = await seatalk.send_clarify("group/G1", "Proceed?", ["Yes", "No"], CID, "sess")

    assert result.success is True
    assert client.sent[0][2]["tag"] == "interactive_message"
    assert seatalk._clarify_claimed == {}
    assert fake_clarify.awaited == [CID]


@pytest.mark.asyncio
async def test_t14_14_card_send_failure_falls_back_to_text(fake_clarify):
    client = FakeClarifyClient(card_send_error=RuntimeError("boom"))
    seatalk = adapter.SeaTalkAdapter(_config(client))

    result = await seatalk.send_clarify("group/G1", "Proceed?", ["Yes", "No"], CID, "sess")

    assert result.success is True
    assert client.sent[0][2]["tag"] == "text"
    assert seatalk._clarify_claimed == {}


@pytest.mark.asyncio
async def test_t14_14b_over_budget_delivers_nothing(fake_clarify, monkeypatch):
    monkeypatch.setattr(adapter, "CLARIFY_SEND_TIMEOUT_SECONDS", 0.01)

    class SlowClient(FakeClarifyClient):
        async def send_group_chat(self, group_id, message, thread_id=None):
            await asyncio.sleep(0.5)
            return await super().send_group_chat(group_id, message, thread_id)

    client = SlowClient()
    seatalk = adapter.SeaTalkAdapter(_config(client))

    result = await seatalk.send_clarify("group/G1", "Proceed?", ["Yes", "No"], CID, "sess")

    # The caller has already given up, so a late card or list would land unanswerable.
    assert result.success is False
    assert client.sent == []

@pytest.mark.asyncio
async def test_t14_15_choice_click_resolves_and_closes(fake_clarify):
    client = FakeClarifyClient()
    seatalk = await _sent_card(client, choices=("Yes", "No", "Again"))

    await seatalk.handle_clarify_click(clarify_id=CID, index=1, card=_card())

    assert fake_clarify.resolved == [(CID, "No")]
    assert f"{clarify_card.CHOSEN_OPTION} No" in _closed_text(client)


@pytest.mark.asyncio
async def test_t14_16_second_click_is_ignored(fake_clarify):
    client = FakeClarifyClient()
    seatalk = await _sent_card(client)

    await seatalk.handle_clarify_click(clarify_id=CID, index=0, card=_card())
    await seatalk.handle_clarify_click(clarify_id=CID, index=1, card=_card())

    assert fake_clarify.resolved == [(CID, "Yes")]
    assert len(client.updates) == 1


@pytest.mark.asyncio
async def test_t14_16b_click_on_a_card_this_process_never_sent(fake_clarify):
    client = FakeClarifyClient(
        fetched={
            "code": 0,
            "interactive_message": {
                "last_edited_time": 0,
                "elements": clarify_card.build_clarify_elements(
                    question="Proceed?", choices=["Yes", "No"], clarify_id=CID
                ),
            },
        }
    )
    seatalk = adapter.SeaTalkAdapter(_config(client))

    await seatalk.handle_clarify_click(clarify_id=CID, index=1, card=_card())

    assert fake_clarify.resolved == [(CID, "No")]
    assert f"{clarify_card.CHOSEN_OPTION} No" in _closed_text(client)


@pytest.mark.asyncio
async def test_t14_16c_same_message_id_on_another_account_is_not_a_repeat(fake_clarify):
    client = FakeClarifyClient()
    second = FakeClarifyClient(
        fetched={
            "code": 0,
            "interactive_message": {
                "last_edited_time": 0,
                "elements": clarify_card.build_clarify_elements(
                    question="Proceed?", choices=["Yes", "No"], clarify_id=CID
                ),
            },
        }
    )
    seatalk = adapter.SeaTalkAdapter(_config(client, second))
    await seatalk.send_clarify("group/G1", "Proceed?", ["Yes", "No"], CID, "sess")

    await seatalk.handle_clarify_click(clarify_id=CID, index=0, card=_card())
    await seatalk.handle_clarify_click(clarify_id=CID, index=1, card=_card(account_id="second"))

    assert fake_clarify.resolved == [(CID, "Yes"), (CID, "No")]
    assert len(client.updates) == 1
    assert len(second.updates) == 1


@pytest.mark.asyncio
async def test_t14_17_expired_choice_click_shows_the_status(fake_clarify):
    fake_clarify.resolve_ok = False
    client = FakeClarifyClient()
    seatalk = await _sent_card(client)

    await seatalk.handle_clarify_click(clarify_id=CID, index=0, card=_card())

    assert _closed_text(client) == f"{clarify_card.CLOSED_DIVIDER}\n_This question is no longer open._"


@pytest.mark.asyncio
async def test_t14_18_other_click_closes_the_card(fake_clarify):
    client = FakeClarifyClient()
    seatalk = await _sent_card(client)

    await seatalk.handle_clarify_click(clarify_id=CID, index=None, card=_card())

    # Once on send, once on the tap, whose return value says the prompt is still open.
    assert fake_clarify.awaited == [CID, CID]
    assert fake_clarify.resolved == []
    text = _closed_text(client)
    assert f"{clarify_card.CHOSEN_OPTION} {clarify_card.CLARIFY_OTHER_LABEL}" in text
    assert text.count(clarify_card.CHOSEN_OPTION) == 1
    assert "_Reply with your own answer._" in text
    assert client.sent[-1][2]["text"]["content"] == "Reply with your own answer."


@pytest.mark.asyncio
async def test_t14_19_other_click_on_a_dead_prompt_says_so(fake_clarify):
    fake_clarify.await_ok = False
    client = FakeClarifyClient()
    seatalk = await _sent_card(client)

    await seatalk.handle_clarify_click(clarify_id=CID, index=None, card=_card())

    assert _closed_text(client) == f"{clarify_card.CLOSED_DIVIDER}\n_This question is no longer open._"
    assert client.sent[-1][2]["text"]["content"] == "This question is no longer open."


@pytest.mark.asyncio
async def test_t14_20_already_edited_card_is_left_alone(fake_clarify):
    client = FakeClarifyClient(
        fetched={"code": 0, "interactive_message": {"last_edited_time": 9, "elements": []}}
    )
    seatalk = await _sent_card(client)

    await seatalk.handle_clarify_click(clarify_id=CID, index=0, card=_card())

    assert fake_clarify.resolved == [(CID, "Yes")]
    assert client.updates == []


@pytest.mark.asyncio
async def test_t14_21_close_failure_falls_back_to_a_notice(fake_clarify):
    client = FakeClarifyClient(update_error=RuntimeError("boom"))
    seatalk = await _sent_card(client, "EmpOne")

    await seatalk.handle_clarify_click(clarify_id=CID, index=0, card=_card("EmpOne"))

    assert client.sent[-1][2]["text"]["content"] == "Answered: Yes"


@pytest.mark.asyncio
async def test_t14_21b_failed_click_releases_the_claim(fake_clarify):
    def boom(clarify_id, response):
        raise RuntimeError("boom")

    fake_clarify.module.resolve_gateway_clarify = boom
    client = FakeClarifyClient()
    seatalk = await _sent_card(client)

    await seatalk.handle_clarify_click(clarify_id=CID, index=0, card=_card())
    assert seatalk._clarify_claimed == {}

    fake_clarify.module.resolve_gateway_clarify = lambda cid, response: (
        fake_clarify.resolved.append((cid, response)) or fake_clarify.resolve_ok
    )
    await seatalk.handle_clarify_click(clarify_id=CID, index=0, card=_card())

    assert fake_clarify.resolved == [(CID, "Yes")]


@pytest.mark.asyncio
async def test_t14_22_missing_entry_uses_a_positional_label(fake_clarify):
    fake_clarify.module._entries.clear()
    client = FakeClarifyClient()
    seatalk = await _sent_card(client)

    await seatalk.handle_clarify_click(clarify_id=CID, index=1, card=_card())

    assert fake_clarify.resolved == [(CID, "choice 2")]


class RecordingAdapter:
    def __init__(self):
        self.clicks = []
        self.inbound_events = []

    async def handle_clarify_click(self, **kwargs):
        self.clicks.append(kwargs)


def _click_payload(**event):
    base = {
        "message_id": "card-1",
        "employee_code": "EmpOne",
        "email": "one@example.com",
        "value": f"stc1:{CID}:1",
        "group_id": "GroupABC",
        "thread_id": "thr-1",
    }
    base.update(event)
    return {"event_type": "interactive_message_click", "event_id": "evt-1", "event": base}


def _dispatcher(fake_adapter, **kwargs):
    return SeaTalkEventDispatcher(
        adapter=fake_adapter,
        client=FakeClarifyClient(),
        app_id="app-id",
        debounce_idle_seconds=0,
        debounce_max_seconds=0,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_t14_23_click_reaches_the_adapter():
    fake_adapter = RecordingAdapter()
    dispatcher = _dispatcher(fake_adapter, group_policy="open")

    await dispatcher.dispatch(_click_payload(), "webhook")

    assert fake_adapter.clicks == [
        {
            "clarify_id": CID,
            "index": 1,
            "card": _card("group/GroupABC", thread_id="thr-1", account_id=None),
        }
    ]


@pytest.mark.asyncio
async def test_t14_24_redelivered_click_is_dropped():
    fake_adapter = RecordingAdapter()
    dispatcher = _dispatcher(fake_adapter, group_policy="open")

    await dispatcher.dispatch(_click_payload(), "webhook")
    await dispatcher.dispatch(_click_payload(), "webhook")

    assert len(fake_adapter.clicks) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"group_policy": "disabled"},
        {"group_policy": "allowlist", "group_allowlist": {"Other"}},
        {"group_policy": "open", "group_sender_allowlist": {"EmpTwo"}},
    ],
)
async def test_t14_25_group_policies_reject_the_click(kwargs):
    fake_adapter = RecordingAdapter()
    dispatcher = _dispatcher(fake_adapter, **kwargs)

    await dispatcher.dispatch(_click_payload(), "webhook")

    assert fake_adapter.clicks == []


@pytest.mark.asyncio
async def test_t14_26_dm_click_uses_the_dm_policy():
    fake_adapter = RecordingAdapter()
    dispatcher = _dispatcher(fake_adapter, dm_policy="allowlist", allowlist={"EmpTwo"})

    await dispatcher.dispatch(_click_payload(group_id=None), "webhook")

    assert fake_adapter.clicks == []


@pytest.mark.asyncio
async def test_t14_27_foreign_value_never_reaches_the_adapter():
    fake_adapter = RecordingAdapter()
    dispatcher = _dispatcher(fake_adapter, group_policy="open")

    await dispatcher.dispatch(_click_payload(value="stq1:ask_x:0"), "webhook")

    assert fake_adapter.clicks == []
