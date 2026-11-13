"""Fill the TTS cache with every conversation topic (SPEC §6, §8), so 💡 costs nothing later.

For the active TTS provider and the backup provider (TTS_FALLBACK_PROVIDER), with the first
pt-BR voice of each (the default voice the app uses). Prints the characters it will use and
asks for confirmation. Topics already in the cache are skipped; every request is recorded in
usage_events. A provider at 95% of its monthly allowance is skipped.

Usage (from backend/, Docker running):  python -m scripts.precompute_topic_audio [--yes]
"""

import argparse
import asyncio
import sys

from app import database
from app.config import get_settings
from app.services import usage
from app.services.topics import load_topics
from app.services.tts.base import TtsError, TtsProvider
from app.services.tts.cache import DbTtsCache, cache_key
from app.services.tts.chain import build_active_provider, build_backup_provider

LANG = "pt-BR"


def confirm() -> bool:
    return input("Continue? [y/N] ").strip().lower() in ("y", "yes", "s", "sim", "t", "tak")


async def run(yes: bool) -> int:
    settings = get_settings()
    database.init_engine(settings.database_url)
    cache = DbTtsCache(settings.tts_cache_max_mb)
    texts = [t.text for t in load_topics() if t.lang == LANG]
    allowances = {settings.tts_provider: settings.tts_monthly_chars}
    if settings.tts_fallback_provider:
        allowances[settings.tts_fallback_provider] = settings.tts_fallback_monthly_chars

    plan: list[tuple[TtsProvider, str, list[str]]] = []
    for provider in (build_active_provider(settings), build_backup_provider(settings)):
        if provider is None:
            continue
        voices = provider.voices(LANG)
        if not voices:
            print(f"{provider.name}: no {LANG} voices configured, skipped.")
            continue
        voice = voices[0].id
        missing = [
            t
            for t in texts
            if await cache.get(cache_key(provider.name, voice, provider.model, 1.0, t)) is None
        ]
        async with database.session_factory()() as db:
            used = await usage.tts_chars_month(db, provider.name)
        allowance = allowances.get(provider.name, 0)
        chars = sum(len(t) for t in missing)
        if allowance and used + chars > 0.95 * allowance:
            print(
                f"{provider.name}: {chars} chars would pass 95% of the allowance "
                f"({used}/{allowance}), skipped."
            )
            continue
        print(
            f"{provider.name} ({voice}): {len(missing)} of {len(texts)} topics to synthesize, "
            f"~{chars} characters (this month: {used}/{allowance or '∞'})."
        )
        if missing:
            plan.append((provider, voice, missing))

    total = sum(len(t) for _, _, m in plan for t in m)
    if not plan:
        print("Nothing to do.")
        await database.dispose_engine()
        return 0
    print(
        f"Total: ~{total} characters (PRICE_TTS_PER_1K_CHARS={settings.price_tts_per_1k_chars} → "
        f"~US$ {total / 1000 * settings.price_tts_per_1k_chars:.2f})."
    )
    if not yes and not await asyncio.to_thread(confirm):
        print("Cancelled.")
        await database.dispose_engine()
        return 1

    for provider, voice, missing in plan:
        done = failed = 0
        for text in missing:
            try:
                audio = b"".join(
                    [chunk async for chunk in provider.synthesize_stream(text, LANG, voice)]
                )
            except TtsError as exc:
                failed += 1
                print(f"  {provider.name}: failed ({exc.code}) for: {text[:50]}")
                continue
            async with database.session_factory()() as db:
                await usage.record_tts(
                    db, user_id=None, provider=provider.name, model=provider.model, chars=len(text)
                )
            await cache.put(
                cache_key(provider.name, voice, provider.model, 1.0, text),
                provider=provider.name,
                voice_id=voice,
                model=provider.model,
                mime=provider.mime,
                audio=audio,
            )
            done += 1
        print(f"{provider.name}: {done} cached, {failed} failed.")
    await database.dispose_engine()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    sys.exit(asyncio.run(run(parser.parse_args().yes)))


if __name__ == "__main__":
    main()
