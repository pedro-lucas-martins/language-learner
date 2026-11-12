"""WebSocket protocol (SPEC §7). Mirrored in frontend/src/protocol.ts — change both together.

Slice 2 adds voice: audio in, audio out, barge-in and metrics. Later slices add feedback
and topics.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

Lang = Literal["pt-BR", "pl-PL"]
Level = Literal["A1", "A2", "B1", "B2", "C1"]
ErrorCode = Literal["quota_exceeded", "provider_unavailable", "stt_failed", "bad_request"]

MAX_USER_TEXT = 1000
MAX_MIME = 100


class _Msg(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- client → server ------------------------------------------------------------


class AuthMsg(_Msg):
    type: Literal["auth"]
    token: str = Field(max_length=200)


class UserTextMsg(_Msg):
    type: Literal["user_text"]
    text: str = Field(min_length=1, max_length=MAX_USER_TEXT)


class SetLevelMsg(_Msg):
    type: Literal["set_level"]
    level: Level


class StartOfSpeechMsg(_Msg):
    type: Literal["start_of_speech"]
    mime: str = Field(min_length=1, max_length=MAX_MIME)
    purpose: Literal["utterance", "pron_retry"] = "utterance"
    target_word: str | None = Field(default=None, max_length=80)
    message_id: str | None = Field(default=None, max_length=80)


class EndOfSpeechMsg(_Msg):
    type: Literal["end_of_speech"]


class UserStartedSpeakingMsg(_Msg):
    type: Literal["user_started_speaking"]


ClientMsg = Annotated[
    AuthMsg
    | UserTextMsg
    | SetLevelMsg
    | StartOfSpeechMsg
    | EndOfSpeechMsg
    | UserStartedSpeakingMsg,
    Field(discriminator="type"),
]
client_msg_adapter: TypeAdapter[ClientMsg] = TypeAdapter(ClientMsg)


# --- server → client ------------------------------------------------------------


class UserInfo(BaseModel):
    name: str
    native_lang: Lang
    target_lang: Lang
    level: Level
    recast_pronunciation: bool


class ReadyMsg(BaseModel):
    type: Literal["ready"] = "ready"
    user: UserInfo
    session_id: str


class UserUpdatedMsg(BaseModel):
    type: Literal["user_updated"] = "user_updated"
    user: UserInfo


class TranscriptMsg(BaseModel):
    type: Literal["transcript"] = "transcript"
    message_id: str
    text: str


class AiTextDeltaMsg(BaseModel):
    type: Literal["ai_text_delta"] = "ai_text_delta"
    message_id: str
    delta: str


class AiTextDoneMsg(BaseModel):
    type: Literal["ai_text_done"] = "ai_text_done"
    message_id: str
    text: str


class UsageMsg(BaseModel):
    type: Literal["usage"] = "usage"
    month_usd_est: float
    budget_usd: float
    tts_chars_month: int
    tts_chars_allowance: int
    tts_provider_active: str


class AudioMetaMsg(BaseModel):
    """Precedes every binary audio frame. `final` marks the last chunk of a sentence."""

    type: Literal["audio_meta"] = "audio_meta"
    message_id: str
    seq: int
    sentence: int
    mime: str
    final: bool


class TtsFallbackMsg(BaseModel):
    type: Literal["tts_fallback"] = "tts_fallback"
    message_id: str
    sentence: int
    text: str
    lang: Lang


class InterruptedMsg(BaseModel):
    type: Literal["interrupted"] = "interrupted"
    message_id: str


class MetricsMsg(BaseModel):
    type: Literal["metrics"] = "metrics"
    message_id: str
    stt_ms: int | None
    llm_first_token_ms: int | None
    first_audio_ms: int | None
    total_ms: int


class ErrorMsg(BaseModel):
    type: Literal["error"] = "error"
    code: ErrorCode
    message: str


ServerMsg = (
    ReadyMsg
    | UserUpdatedMsg
    | TranscriptMsg
    | AiTextDeltaMsg
    | AiTextDoneMsg
    | AudioMetaMsg
    | TtsFallbackMsg
    | InterruptedMsg
    | MetricsMsg
    | UsageMsg
    | ErrorMsg
)
