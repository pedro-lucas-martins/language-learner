"""Prompt construction (SPEC §4.1). Static content first, per-user content last."""

from app.services.memory import Turn

LANG_NAMES = {"pl-PL": "Polish", "pt-BR": "Brazilian Portuguese"}

_PERSONA = {
    "pl-PL": (
        "You are Kasia, a friendly young woman from Kraków chatting with a Brazilian friend "
        "who is learning Polish. You are curious about Brazil and happy to talk about everyday "
        "life in Poland."
    ),
    "pt-BR": (
        "Você é a Bia, uma jovem simpática de Belo Horizonte conversando com um amigo polonês "
        "que está aprendendo português. You are curious about Poland and happy to talk about "
        "everyday life in Brazil."
    ),
}

_DIRECTION_NOTES = {
    "pl-PL": (
        "The learner's native language is Brazilian Portuguese. Typical difficulties: the seven "
        "cases, verbal aspect, the lack of articles, consonant clusters. Keep your Polish natural "
        "and correct; never switch to Portuguese unless the learner is completely lost, and then "
        "use at most a few words before returning to Polish."
    ),
    "pt-BR": (
        "The learner's native language is Polish. Typical difficulties: articles, ser vs estar, "
        "pretérito perfeito vs imperfeito, the subjunctive, nasal vowels. Keep your Portuguese "
        "natural, colloquial Brazilian (use 'você', 'a gente'); never switch to Polish unless the "
        "learner is completely lost, and then use at most a few words before returning to "
        "Portuguese."
    ),
}

_LEVEL_RULES = {
    "A1": "Level A1: very common words only, present tense, sentences of at most 8 words. "
    "End with one simple yes/no or either/or question.",
    "A2": "Level A2: common everyday vocabulary, present and simple past, sentences of at most "
    "12 words. End with one simple question.",
    "B1": "Level B1: natural everyday speech, a few common idioms, open questions.",
    "B2": "Level B2: natural everyday speech with idioms and varied tenses, open questions that "
    "invite opinions.",
    "C1": "Level C1: native register, idioms and some slang, debate-style questions.",
}


RECAST_RULE = (
    "Pronunciation recast: the learner's last message comes with their recorded voice and its "
    "transcript. If they clearly mispronounced a word, reuse that same word, correctly, "
    "naturally in your reply so they hear it said right, the way a friend would echo it. At "
    "most once per reply. Never say they pronounced it wrong and never explain anything. If "
    "nothing was clearly mispronounced, just reply normally."
)


NO_CORRECTION_RULE = (
    "Never explain grammar, never correct the learner explicitly, never list mistakes. "
    "Corrections are shown elsewhere in the app."
)

_BEGINNER_LEVELS = ("A1", "A2")


def correction_rule(*, level: str, target_lang: str, explain_lang: str) -> str:
    """Correction in the conversation (SPEC §4.1): one mistake, then carry on."""
    target, explain = LANG_NAMES[target_lang], LANG_NAMES[explain_lang]
    rule = (
        "Correction in the conversation: if the learner's last message has a clear mistake, "
        "start your reply by correcting ONE mistake only (the most important one): say the "
        "correct form naturally, the way a friendly native would (for example: 'We say X.'), "
        "then carry on with the conversation in the same reply as usual. Never correct more "
        "than one thing, never list mistakes, never give a lecture. Only correct a mistake you "
        "are sure about: never 'correct' a form that is already right, and never repeat the "
        "learner's own correct words as if they were a correction. If there is no clear "
        "mistake, do not correct anything. The correction counts toward your length limit: "
        "at most two short sentences in total (correction included), then one short question."
    )
    if level in _BEGINNER_LEVELS and explain_lang != target_lang:
        rule += (
            f" Because the learner is a beginner, right after the correct form add ONE short "
            f"sentence in {explain} saying why (this is the only exception to replying in "
            f"{target}, and it does not count toward the length limit), then continue in "
            f"{target}."
        )
    else:
        rule += f" Say the correction in {target} only; do not explain the rule."
    return rule


def chat_system_prompt(
    *,
    target_lang: str,
    native_lang: str,
    level: str,
    user_facts: str,
    summary: str,
    recast: bool = False,
    correct: bool = False,
    explain_lang: str | None = None,
) -> str:
    """System prompt for Track 1 (conversation).

    `recast`: the last message has audio. `correct`: correction in the conversation is on;
    `explain_lang` (the learner's ui_lang) is used for the beginners' one-sentence reason.
    """
    lang = LANG_NAMES[target_lang]
    static = (
        f"{_PERSONA[target_lang]}\n\n"
        "Rules:\n"
        f"- Reply ONLY in {lang}.\n"
        "- Reply like a friend in a spoken conversation: 1 or 2 short sentences, then exactly "
        "one short question that keeps the conversation going.\n"
        "- No emojis, no markdown, no lists: your text is read aloud.\n"
        "- If the learner writes in their native language, answer in "
        f"{lang} using simple words.\n\n"
        f"{_DIRECTION_NOTES[target_lang]}"
    )
    parts = [static, _LEVEL_RULES[level]]
    if correct:
        parts.append(
            correction_rule(
                level=level, target_lang=target_lang, explain_lang=explain_lang or native_lang
            )
        )
    else:
        parts.append(NO_CORRECTION_RULE)
    if recast:
        parts.append(RECAST_RULE)
    if user_facts.strip():
        parts.append(f"What you know about the learner from earlier conversations:\n{user_facts}")
    if summary.strip():
        parts.append(f"Summary of this conversation so far:\n{summary}")
    _ = native_lang  # direction is fully determined by target_lang for this language pair
    return "\n\n".join(parts)


SUMMARY_SYSTEM_PROMPT = (
    "You maintain a running summary of a language-practice conversation. Merge the previous "
    "summary with the new turns into ONE summary of at most 40 words, in English, keeping only "
    "what matters to continue the conversation: topics discussed, facts the learner shared, "
    "open questions. Output only the summary text."
)


def summary_user_prompt(previous: str, turns: list[Turn]) -> str:
    lines = [f"Previous summary: {previous or '(none)'}", "New turns:"]
    for turn in turns:
        lines.append(f"Learner: {turn.user}")
        lines.append(f"Friend: {turn.ai}")
    return "\n".join(lines)


def truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    return " ".join(words[:max_words])
