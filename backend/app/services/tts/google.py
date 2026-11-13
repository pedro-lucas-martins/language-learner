"""Google Cloud Text-to-Speech, Chirp 3 HD voices, gRPC streaming synthesis (SPEC §6)."""

import logging
from collections.abc import AsyncIterator

from app.config import LangCode, Settings, Voice
from app.services.tts.base import TtsError, with_timeouts

log = logging.getLogger(__name__)


class GoogleTts:
    name = "google"
    model = "chirp3-hd"
    mime = "audio/ogg;codecs=opus"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None

    def voices(self, lang: LangCode) -> list[Voice]:
        return self._settings.tts_voices("google", lang)

    def _get_client(self):  # type: ignore[no-untyped-def]
        if not self._settings.google_application_credentials:
            raise TtsError("not_configured", "GOOGLE_APPLICATION_CREDENTIALS is empty")
        if self._client is None:
            # Imported lazily: heavy gRPC import, unused in tests.
            from google.cloud import texttospeech
            from google.oauth2 import service_account

            try:
                credentials = service_account.Credentials.from_service_account_file(
                    self._settings.google_application_credentials
                )
            except (OSError, ValueError) as exc:
                raise TtsError("not_configured", f"invalid credentials file: {exc}") from exc
            self._client = texttospeech.TextToSpeechAsyncClient(credentials=credentials)
        return self._client

    async def warm(self) -> None:
        """Open the gRPC channel with a free call (voice list)."""
        await self._get_client().list_voices(language_code="pl-PL")

    @staticmethod
    def _map_error(exc: Exception) -> TtsError:
        from google.api_core import exceptions as gexc

        if isinstance(exc, TtsError):
            return exc
        if isinstance(exc, gexc.ResourceExhausted):
            return TtsError("quota", str(exc))
        if isinstance(
            exc, gexc.ServiceUnavailable | gexc.InternalServerError | gexc.DeadlineExceeded
        ):
            return TtsError("unavailable", str(exc))
        if isinstance(exc, gexc.GoogleAPICallError):
            return TtsError("bad_request", str(exc))
        log.exception("Unexpected Google TTS error")
        return TtsError("unavailable", type(exc).__name__)

    async def _raw_stream(
        self, text: str, lang: LangCode, voice_id: str, speaking_rate: float
    ) -> AsyncIterator[bytes]:
        from google.cloud import texttospeech as tts

        client = self._get_client()
        config = tts.StreamingSynthesizeConfig(
            voice=tts.VoiceSelectionParams(language_code=lang, name=voice_id),
            streaming_audio_config=tts.StreamingAudioConfig(
                audio_encoding=tts.AudioEncoding.OGG_OPUS, speaking_rate=speaking_rate
            ),
        )

        async def requests() -> AsyncIterator[tts.StreamingSynthesizeRequest]:
            yield tts.StreamingSynthesizeRequest(streaming_config=config)
            yield tts.StreamingSynthesizeRequest(input=tts.StreamingSynthesisInput(text=text))

        try:
            responses = await client.streaming_synthesize(requests=requests())
            async for response in responses:
                if response.audio_content:
                    yield response.audio_content
        except Exception as exc:  # noqa: BLE001 — mapped to a typed error
            raise self._map_error(exc) from exc

    def synthesize_stream(
        self, text: str, lang: LangCode, voice_id: str, speaking_rate: float = 1.0
    ) -> AsyncIterator[bytes]:
        return with_timeouts(self._raw_stream(text, lang, voice_id, speaking_rate))
