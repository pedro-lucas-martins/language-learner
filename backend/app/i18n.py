"""User-facing server messages, in the learner's native language (SPEC §1)."""

from app.protocol import ErrorCode

_ERRORS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "quota_exceeded": "Você atingiu o limite de uso de hoje. Volte amanhã!",
        "provider_unavailable": "A IA está indisponível no momento. Tente de novo em instantes.",
        "not_configured": "A IA ainda não foi configurada no servidor (chave ou modelo do Gemini).",
        "stt_failed": "Não consegui entender o áudio. Tente de novo.",
        "bad_request": "Mensagem inválida.",
        "interrupted": "A resposta foi interrompida. Tente de novo.",
    },
    "pl-PL": {
        "quota_exceeded": "Osiągnięto dzisiejszy limit użycia. Wróć jutro!",
        "provider_unavailable": "AI jest teraz niedostępna. Spróbuj ponownie za chwilę.",
        "not_configured": (
            "AI nie jest jeszcze skonfigurowana na serwerze (klucz lub model Gemini)."
        ),
        "stt_failed": "Nie udało się zrozumieć nagrania. Spróbuj ponownie.",
        "bad_request": "Nieprawidłowa wiadomość.",
        "interrupted": "Odpowiedź została przerwana. Spróbuj ponownie.",
    },
}


def error_text(lang: str, key: str) -> str:
    table = _ERRORS.get(lang, _ERRORS["pt-BR"])
    return table.get(key, table["bad_request"])


def wire_code(key: str) -> ErrorCode:
    """Map internal reasons to the protocol's error codes."""
    if key == "quota_exceeded":
        return "quota_exceeded"
    if key == "stt_failed":
        return "stt_failed"
    if key == "bad_request":
        return "bad_request"
    return "provider_unavailable"
