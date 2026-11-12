"""Track 2: grammar + pronunciation feedback (SPEC §5).

Runs beside the conversation, never inside it. Voice turns send the audio and the verbatim
transcript (grammar + pronunciation); typed turns and regrades send text only (grammar).
Explanations are written in the learner's native language.

The model's JSON is validated strictly. Anything invalid is dropped and logged — the
learner simply gets no correction for that message.
"""

import asyncio
import json
import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.protocol import GrammarError, PronIssue
from app.services.llm import AudioInput, LlmError, LlmProvider, LlmUsage
from app.services.prompts import LANG_NAMES

log = logging.getLogger(__name__)

MIN_WORDS = 3
MAX_ITEMS = 3
FEEDBACK_MAX_OUTPUT_TOKENS = 900
FEEDBACK_TEMPERATURE = 0.1
RETRY_DELAY_S = 0.6

Source = Literal["audio", "text"]
# (role, model, usage) — role is "feedback", or "utility" when over budget (priced as such).
RecordFeedback = Callable[[str, str, LlmUsage], Awaitable[None]]

_GRAMMAR_FOCUS = {
    "pl-PL": (
        "the 7 cases (mianownik, dopełniacz, celownik, biernik, narzędnik, miejscownik, "
        "wołacz) and case after prepositions and verbs; verbal aspect (dokonany/niedokonany); "
        "there are no articles in Polish; gender agreement, including past-tense verb endings "
        "(-łem/-łam); numerals with the genitive (pięć kotów)"
    ),
    "pt-BR": (
        "articles (o/a/um/uma) and their contractions with prepositions (no, na, do, da, ao); "
        "ser vs estar; pretérito perfeito vs imperfeito; the subjunctive; gender and number "
        "agreement; prepositions"
    ),
}

_PRON_FOCUS = {
    "pl-PL": (
        "sz / ś / s; cz / ć / c; rz-ż / ź / z; dz, dż, dź; ł (like English w, never l); nasal "
        "ą / ę (and their denasalization before stops); y vs i; stress on the penultimate "
        "syllable; no extra vowel after final consonants; no vowel reduction"
    ),
    "pt-BR": (
        "nasal vowels and diphthongs (ão, õe, ãe, final -em/-im); open vs closed é/ê and ó/ô; "
        "lh and nh; r / rr and the soft r between vowels; final unstressed -e ≈ i and -o ≈ u; "
        "t/d before i (tchi, dji); s/z between vowels; word stress (avó vs avô)"
    ),
}


_EXAMPLE_RULE = {
    "pt-BR": "Depois de 'do', o substantivo vai para o genitivo: sklep → sklepu.",
    "pl-PL": "Po 'gostar' zawsze jest przyimek 'de': gosto de café.",
}


def feedback_system_prompt(target_lang: str, native_lang: str, *, with_audio: bool) -> str:
    target, native = LANG_NAMES[target_lang], LANG_NAMES[native_lang]
    lines = [
        f"You are a precise, kind {target} teacher. The learner's native language is {native}.",
        "Analyse ONLY the learner's message. Answer with one JSON object and nothing else.",
        f"LANGUAGE: every explanation field (r, p, tip) MUST be written in {native}. Never "
        f"in English. Only the quoted {target} words themselves stay in {target}.",
        "",
        "GRAMMAR",
        f"- Report real mistakes in {target}: at most {MAX_ITEMS}, most important first.",
        f"- Pay special attention to: {_GRAMMAR_FOCUS[target_lang]}.",
        '- "e": the wrong part, copied EXACTLY from the message (a substring).',
        '- "c": the corrected form of that part.',
        f'- "r": the rule in one short sentence, written in {native}.',
        f'- "p": a short {native}⇄{target} contrast tip written in {native}, or "".',
        f'- Style example for "r": {_EXAMPLE_RULE[native_lang]!r}.',
        "- Do not report punctuation, capitalization, accents left out when typing, informal "
        f"but correct style, or words the learner said in {native} on purpose.",
    ]
    if with_audio:
        lines += [
            "",
            "PRONUNCIATION (from the attached recording)",
            f"- At most {MAX_ITEMS} words, most important first.",
            f"- Pay special attention to: {_PRON_FOCUS[target_lang]}.",
            "- Report only issues that change the meaning or clearly mark a foreign accent "
            '("sev": "major"), or that repeat in the recording ("sev": "minor"). Ignore a '
            "normal accent and fast-speech reductions. When unsure, do NOT report.",
            "- Only words that appear in the transcript. Never invent words.",
            '- "w": the word spelled correctly; "heard": an approximation of what was said, '
            "in Latin letters;",
            f'  "tip": one practical articulation tip written in {native}.',
        ]
    lines += [
        "",
        "OUTPUT",
        'If there is nothing to report: {"ok": true, "errs": [], "pron": []}. Otherwise:',
        '{"ok": false, "errs": [{"e": "...", "c": "...", "r": "...", "p": "..."}], '
        '"pron": [{"w": "...", "heard": "...", "tip": "...", "sev": "major"}]}',
    ]
    if not with_audio:
        lines.append('There is no recording: "pron" must be [].')
    return "\n".join(lines)


def feedback_user_prompt(text: str, *, with_audio: bool) -> str:
    label = "Verbatim transcript of the recording" if with_audio else "Learner's message"
    return f"{label}:\n{text}"


class _RawFeedback(BaseModel):
    """What the model returns. Items are validated one by one in `parse_feedback`."""

    ok: bool
    errs: list[dict[str, object]] = []
    pron: list[dict[str, object]] = []


@dataclass(frozen=True)
class FeedbackResult:
    ok: bool
    errs: list[GrammarError]
    pron: list[PronIssue]

    def as_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "errs": [e.model_dump() for e in self.errs],
                "pron": [p.model_dump() for p in self.pron],
            },
            ensure_ascii=False,
        )


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", folded).strip()


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", _norm(text)))


def parse_feedback(raw: str, message: str, *, with_audio: bool) -> FeedbackResult | None:
    """Validate the model's JSON. Returns None when it is unusable.

    Grammar items whose `e` is not in the message, and pronunciation items for words that
    were not said, are dropped (SPEC §5: never report what was not said).
    """
    try:
        data = _RawFeedback.model_validate_json(_strip_fence(raw))
    except ValidationError as exc:
        log.warning("Feedback JSON rejected: %s", exc.errors()[:2])
        return None
    norm_message = _norm(message)
    said = _words(message)
    errs: list[GrammarError] = []
    for item in data.errs:
        try:
            err = GrammarError.model_validate(item)
        except ValidationError:
            continue
        if err.e.strip() and _norm(err.e) in norm_message and _norm(err.e) != _norm(err.c):
            errs.append(err)
    pron: list[PronIssue] = []
    if with_audio:
        for item in data.pron:
            try:
                issue = PronIssue.model_validate(item)
            except ValidationError:
                continue
            # A word that was "heard" exactly as written was not mispronounced.
            heard_same = _norm(issue.heard).strip(".!?, ") == _norm(issue.w)
            if _words(issue.w) and _words(issue.w) <= said and not heard_same:
                pron.append(issue)
    errs, pron = errs[:MAX_ITEMS], pron[:MAX_ITEMS]
    return FeedbackResult(ok=not errs and not pron, errs=errs, pron=pron)


def _strip_fence(raw: str) -> str:
    """Some models wrap JSON in ```json fences despite the instructions."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{") :] if "{" in raw else raw
    return raw


_STR = {"type": "string"}
# Enforced by Gemini (structured output), so the reply is always well-formed JSON.
FEEDBACK_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "errs": {
            "type": "array",
            "maxItems": MAX_ITEMS,
            "items": {
                "type": "object",
                "properties": {"e": _STR, "c": _STR, "r": _STR, "p": _STR},
                "required": ["e", "c", "r", "p"],
            },
        },
        "pron": {
            "type": "array",
            "maxItems": MAX_ITEMS,
            "items": {
                "type": "object",
                "properties": {
                    "w": _STR,
                    "heard": _STR,
                    "tip": _STR,
                    "sev": {"type": "string", "enum": ["major", "minor"]},
                },
                "required": ["w", "heard", "tip", "sev"],
            },
        },
    },
    "required": ["ok", "errs", "pron"],
}


def needs_feedback(text: str) -> bool:
    return len(text.split()) >= MIN_WORDS


def feedback_model(settings: Settings, *, budget_exceeded: bool) -> str:
    """The feedback model, or the cheapest configured one once over budget (SPEC §1)."""
    if budget_exceeded and settings.gemini_utility_model:
        return settings.gemini_utility_model
    return settings.gemini_feedback_model or settings.gemini_utility_model


async def analyze(
    llm: LlmProvider,
    settings: Settings,
    *,
    text: str,
    audio: AudioInput | None,
    target_lang: str,
    native_lang: str,
    budget_exceeded: bool,
    record: RecordFeedback,
) -> FeedbackResult | None:
    """Run Track 2 once (one retry for transient errors). None = no usable feedback."""
    model = feedback_model(settings, budget_exceeded=budget_exceeded)
    if not model:
        return None
    with_audio = audio is not None
    system = feedback_system_prompt(target_lang, native_lang, with_audio=with_audio)
    prompt = feedback_user_prompt(text, with_audio=with_audio)
    for attempt in range(2):
        try:
            raw, used = await llm.analyze(
                model=model,
                system=system,
                prompt=prompt,
                audio=audio,
                max_output_tokens=FEEDBACK_MAX_OUTPUT_TOKENS,
                temperature=FEEDBACK_TEMPERATURE,
                json_schema=FEEDBACK_JSON_SCHEMA,
            )
        except LlmError as exc:
            log.warning("Feedback attempt %d failed: %s", attempt + 1, exc)
            if exc.code in ("bad_request", "not_configured") or attempt == 1:
                return None
            await asyncio.sleep(RETRY_DELAY_S)
            continue
        role = "feedback" if model == settings.gemini_feedback_model else "utility"
        await record(role, model, used)
        return parse_feedback(raw, text, with_audio=with_audio)
    return None
