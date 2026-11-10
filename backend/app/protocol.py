"""WebSocket protocol (SPEC §7). Mirrored in frontend/src/protocol.ts — change both together.

Slice 1 implements the text subset; later slices add audio, feedback and topics.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

Lang = Literal["pt-BR", "pl-PL"]
Level = Literal["A1", "A2", "B1", "B2", "C1"]
ErrorCode = Literal["quota_exceeded", "provider_unavailable", "stt_failed", "bad_request"]

MAX_USER_TEXT = 1000


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


ClientMsg = Annotated[AuthMsg | UserTextMsg | SetLevelMsg, Field(discriminator="type")]
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


class ErrorMsg(BaseModel):
    type: Literal["error"] = "error"
    code: ErrorCode
    message: str


ServerMsg = (
    ReadyMsg | UserUpdatedMsg | TranscriptMsg | AiTextDeltaMsg | AiTextDoneMsg | UsageMsg | ErrorMsg
)
