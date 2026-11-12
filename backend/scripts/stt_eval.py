"""STT evaluation (SPEC §5): run your own recorded clips through Gemini STT.

Shows each transcript next to what you actually said, so you can see whether the STT
keeps your mistakes (it must not "fix" them). Spends Gemini tokens: prints the
estimated cost and asks for confirmation first. Every call is recorded in usage_events.

Clips live in backend/scripts/stt_clips/ (git-ignored) with an expected.json:
    [{"file": "pl_01.webm", "target_lang": "pl-PL", "native_lang": "pt-BR",
      "expected": "Ja mam dwa kot.", "mispronounced": ["kot"]}]
`mispronounced` is informational until the pronunciation feedback (slice 3).

Usage (from backend/):  python -m scripts.stt_eval [--clips DIR] [--yes]
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from app import database
from app.config import get_settings
from app.services import usage
from app.services.llm import GeminiProvider, LlmUsage
from app.services.stt_service import AUDIO_TOKENS_PER_SECOND, SttError, transcribe

DEFAULT_CLIPS = Path(__file__).with_name("stt_clips")
MIME_BY_EXT = {
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
}


def clip_seconds(path: Path) -> float:
    try:
        import mutagen

        parsed = mutagen.File(path)
        if parsed is not None and parsed.info and parsed.info.length:
            return float(parsed.info.length)
    except Exception:  # noqa: BLE001 — fall back to a size estimate
        pass
    return path.stat().st_size / 4000  # ~32 kbps


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def word_error_rate(expected: str, got: str) -> float:
    ref, hyp = words(expected), words(got)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / len(ref)


def confirm() -> bool:
    return input("Continue? [y/N] ").strip().lower() in ("y", "yes", "s", "sim")


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    clips_dir = Path(args.clips)
    manifest = clips_dir / "expected.json"
    if not manifest.exists():
        print(f"Missing {manifest}. See the docstring at the top of this script.")
        return 1
    clips = json.loads(manifest.read_text(encoding="utf-8"))
    paths = [clips_dir / c["file"] for c in clips]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        print(f"Missing audio files: {', '.join(missing)}")
        return 1
    if not settings.gemini_stt_model or not settings.gemini_api_key:
        print("Set GEMINI_API_KEY and GEMINI_STT_MODEL in .env first.")
        return 1

    seconds = sum(clip_seconds(p) for p in paths)
    tokens = seconds * AUDIO_TOKENS_PER_SECOND
    cost = tokens * settings.price_stt_audio_input_per_m / 1_000_000
    print(f"{len(clips)} clips, ~{seconds:.0f} s of audio, model {settings.gemini_stt_model}")
    print(f"Estimated cost: ~US$ {cost:.4f} (audio input only, from PRICE_STT_AUDIO_INPUT_PER_M)")
    if not args.yes and not await asyncio.to_thread(confirm):
        print("Cancelled.")
        return 1

    database.init_engine(settings.database_url)
    llm = GeminiProvider(settings.gemini_api_key, thinking_level=settings.gemini_thinking_level)

    async def record(model: str, used: LlmUsage, secs: float) -> None:
        async with database.session_factory()() as db:
            await usage.record_stt(db, user_id=None, model=model, usage=used, seconds=secs)

    rates: list[float] = []
    for clip, path in zip(clips, paths, strict=True):
        mime = MIME_BY_EXT.get(path.suffix.lower(), "audio/webm")
        try:
            result = await transcribe(
                llm,
                settings,
                audio=path.read_bytes(),
                mime=mime,
                target_lang=clip["target_lang"],
                native_lang=clip["native_lang"],
                record=record,
            )
            got = result.text
        except SttError as exc:
            got = f"<error: {exc}>"
        wer = word_error_rate(clip["expected"], got)
        rates.append(wer)
        print(f"\n[{path.name}] {clip['target_lang']}  WER {wer:.0%}")
        print(f"  expected: {clip['expected']}")
        print(f"  got:      {got}")
        if clip.get("mispronounced"):
            print(f"  mispronounced on purpose: {', '.join(clip['mispronounced'])}")
    if rates:
        print(f"\nMean WER: {sum(rates) / len(rates):.0%} over {len(rates)} clips")
    await database.dispose_engine()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--clips", default=str(DEFAULT_CLIPS))
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
