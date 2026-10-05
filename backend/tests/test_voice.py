"""Phase 3: Telegram voice notes.

The user's own model transcribes the audio (no separate speech service); the
transcript then runs through the normal Alfred pipeline. All network + model
calls are mocked.
"""

import asyncio

import pytest

import models
from database import SessionLocal
from routers.telegram import handle_telegram_webhook, process_telegram_update
from services import alfred_agent, telegram_service
from services.llm_provider import LLMResponse, ToolCall
from services.llm_providers.base import ProviderCapabilities

SECRET = "test-webhook-secret-12345"
_next_update_id = [9000]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _voice_update(chat_id, duration=5, file_size=1000, mime="audio/ogg"):
    _next_update_id[0] += 1
    return {
        "update_id": _next_update_id[0],
        "message": {
            "message_id": 1,
            "chat": {"id": chat_id},
            "voice": {"file_id": "vf_1", "duration": duration, "file_size": file_size, "mime_type": mime},
        },
    }


class FakeAdapter:
    def __init__(self, audio=True, transcript="buy milk tomorrow", response=None):
        self._audio = audio
        self._transcript = transcript
        self._response = response or LLMResponse(text="Noted, sir.")
        self.transcribe_calls = []
        self.generate_calls = []

    def capabilities(self, model_name=None):
        return ProviderCapabilities(supports_tool_calling=True, supports_audio_input=self._audio)

    async def transcribe_audio(self, audio_bytes, mime_type):
        self.transcribe_calls.append((audio_bytes, mime_type))
        return self._transcript

    async def generate(self, messages, tools, system_instruction=None):
        self.generate_calls.append(messages)
        return self._response


def _use_adapter(monkeypatch, adapter):
    monkeypatch.setattr(alfred_agent, "resolve_adapter_for_user", lambda db, user: adapter)


def _mock_transport(monkeypatch, *, file_path="voice/file_1.oga", audio=b"OggS-bytes"):
    sent = []
    monkeypatch.setattr(telegram_service, "send_telegram_message", lambda *a, **kw: sent.append((a, kw)) or True)
    monkeypatch.setattr(telegram_service, "get_file_path", lambda token, fid, **kw: file_path)
    monkeypatch.setattr(telegram_service, "download_file", lambda token, path, maxb, **kw: audio)
    return sent


def _texts(sent):
    return [a[2] for a, kw in sent]


def _link(client, headers, chat_id):
    code = client.post("/api/account/telegram-link/generate-code", headers=headers).json()["code"]
    db = SessionLocal()
    try:
        assert telegram_service.exchange_link_code(db, code, str(chat_id)) is not None
    finally:
        db.close()


def test_voice_happy_path_transcribes_echoes_and_runs(client, auth_headers, monkeypatch):
    h = auth_headers("voice_happy")
    _link(client, h, 710001)
    adapter = FakeAdapter(transcript="add a mission called buy milk", response=LLMResponse(
        tool_calls=[ToolCall("create_mission", {"title": "buy milk"})]))
    # First generate makes the tool call; the loop then needs a final text turn.
    responses = iter([
        LLMResponse(tool_calls=[ToolCall("create_mission", {"title": "buy milk"})]),
        LLMResponse(text="Logged, sir."),
    ])

    async def gen(messages, tools, system_instruction=None):
        adapter.generate_calls.append(messages)
        return next(responses)

    adapter.generate = gen
    _use_adapter(monkeypatch, adapter)
    sent = _mock_transport(monkeypatch)

    _run(process_telegram_update(_voice_update(710001), None))

    assert adapter.transcribe_calls and adapter.transcribe_calls[0][1] == "audio/ogg"
    texts = _texts(sent)
    assert any(t.startswith("🎙 I heard: add a mission called buy milk") for t in texts)
    assert "Logged, sir." in texts

    db = SessionLocal()
    try:
        user = db.query(models.BatAccount).filter_by(username="voice_happy").first()
        missions = db.query(models.BatMission).filter_by(owner_id=user.id).all()
        assert any(m.title == "buy milk" for m in missions)
        # Only the transcript is stored as the user turn — never audio bytes.
        msgs = db.query(models.BatAlfredMessage).filter_by(owner_id=user.id).all()
        stored_user = [m.content for m in msgs if m.role == "user"]
        assert stored_user == ["add a mission called buy milk"]
        assert all("OggS" not in m.content for m in msgs)
    finally:
        db.close()


def test_voice_unsupported_provider_is_refused_without_download(client, auth_headers, monkeypatch):
    h = auth_headers("voice_noaudio")
    _link(client, h, 710002)
    _use_adapter(monkeypatch, FakeAdapter(audio=False))
    sent = _mock_transport(monkeypatch)
    downloaded = []
    monkeypatch.setattr(telegram_service, "download_file", lambda *a, **kw: downloaded.append(1) or b"x")

    _run(process_telegram_update(_voice_update(710002), None))

    assert _texts(sent) == [alfred_agent.VOICE_UNSUPPORTED_REPLY]
    assert downloaded == []  # never fetched the file for a provider that can't use it


def test_voice_too_long_is_rejected(client, auth_headers, monkeypatch):
    h = auth_headers("voice_long")
    _link(client, h, 710003)
    _use_adapter(monkeypatch, FakeAdapter())
    sent = _mock_transport(monkeypatch)
    _run(process_telegram_update(_voice_update(710003, duration=alfred_agent.MAX_VOICE_SECONDS + 1), None))
    assert _texts(sent) == [alfred_agent.VOICE_TOO_LONG_REPLY]


def test_voice_download_failure_is_reported(client, auth_headers, monkeypatch):
    h = auth_headers("voice_dlfail")
    _link(client, h, 710004)
    _use_adapter(monkeypatch, FakeAdapter())
    sent = _mock_transport(monkeypatch, file_path=None)  # getFile fails
    _run(process_telegram_update(_voice_update(710004), None))
    assert _texts(sent) == [alfred_agent.VOICE_DOWNLOAD_FAIL_REPLY]


def test_voice_empty_transcript_is_reported(client, auth_headers, monkeypatch):
    h = auth_headers("voice_empty")
    _link(client, h, 710005)
    _use_adapter(monkeypatch, FakeAdapter(transcript="   "))
    sent = _mock_transport(monkeypatch)
    _run(process_telegram_update(_voice_update(710005), None))
    assert _texts(sent) == [alfred_agent.VOICE_EMPTY_REPLY]


def test_spoken_delete_still_hits_the_confirmation_gate(client, auth_headers, monkeypatch):
    h = auth_headers("voice_delete")
    _link(client, h, 710006)
    note = client.post("/api/notes", json={"title": "secret plans"}, headers=h).json()
    adapter = FakeAdapter(
        transcript="delete the note called secret plans",
        response=LLMResponse(tool_calls=[ToolCall("delete_note", {"note_id": note["id"]})]),
    )
    _use_adapter(monkeypatch, adapter)
    sent = _mock_transport(monkeypatch)

    _run(process_telegram_update(_voice_update(710006), None))

    texts = _texts(sent)
    assert any("Reply YES to confirm" in t for t in texts)  # gated, not deleted
    assert client.get(f"/api/notes", headers=h).json()  # note still there
    assert any(n["id"] == note["id"] for n in client.get("/api/notes", headers=h).json())


def test_duplicate_voice_update_is_processed_once(client, auth_headers, monkeypatch):
    h = auth_headers("voice_dupe")
    _link(client, h, 710007)
    adapter = FakeAdapter()
    _use_adapter(monkeypatch, adapter)
    _mock_transport(monkeypatch)

    update = _voice_update(710007)
    for _ in range(2):
        client.post("/api/telegram/webhook", json=update,
                    headers={"X-Telegram-Bot-Api-Secret-Token": SECRET})

    assert len(adapter.transcribe_calls) == 1
