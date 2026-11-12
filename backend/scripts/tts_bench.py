"""TTS benchmark (SPEC §6): time to first audio and a blind listening test per provider.

Spends free-tier characters: prints the planned total and asks for confirmation first.
Every request is recorded in `usage_events`, so the database must be reachable.

Usage (from backend/, with the .env at the repository root):
    python -m scripts.tts_bench [--runs 3] [--providers google,elevenlabs] [--limit N] [--yes]
"""

import argparse
import asyncio
import csv
import html
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

from app import database
from app.config import LangCode, Settings, TtsProviderName, get_settings
from app.services import usage
from app.services.tts.base import TtsError, TtsProvider

CORPUS = Path(__file__).with_name("tts_bench_corpus.json")
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "bench_results"
LANGS: tuple[LangCode, ...] = ("pl-PL", "pt-BR")
PROVIDERS: tuple[TtsProviderName, ...] = ("google", "elevenlabs")


@dataclass(frozen=True)
class Item:
    id: str
    lang: LangCode
    kind: str  # "sentence" | "word"
    text: str


@dataclass
class Result:
    provider: str
    lang: str
    item_id: str
    kind: str
    run: int
    chars: int
    ttfa_ms: float | None
    total_ms: float | None
    audio_s: float | None
    error: str = ""


def load_corpus() -> list[Item]:
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    items: list[Item] = []
    for lang in LANGS:
        items += [Item(s["id"], lang, "sentence", s["text"]) for s in data[lang]["sentences"]]
        items += [Item(w["id"], lang, "word", w["text"]) for w in data[lang]["words"]]
    return items


def build_provider(settings: Settings, name: TtsProviderName) -> TtsProvider:
    if name == "google":
        from app.services.tts.google import GoogleTts

        return GoogleTts(settings)
    from app.services.tts.elevenlabs import ElevenLabsTts

    return ElevenLabsTts(settings)


def audio_seconds(data: bytes) -> float | None:
    try:
        import mutagen
    except ImportError:
        return None
    try:
        parsed = mutagen.File(BytesIO(data))
    except Exception:  # noqa: BLE001 — duration is informative only
        return None
    return round(parsed.info.length, 2) if parsed is not None and parsed.info else None


def extension(mime: str) -> str:
    return "ogg" if "ogg" in mime else "mp3"


async def synthesize(
    provider: TtsProvider, item: Item, voice: str
) -> tuple[bytes, float | None, float, str]:
    """Returns (audio, ttfa_ms, total_ms, error). Records usage on the first byte."""
    started = time.perf_counter()
    ttfa: float | None = None
    parts: list[bytes] = []
    try:
        async for chunk in provider.synthesize_stream(item.text, item.lang, voice):
            if ttfa is None:
                ttfa = (time.perf_counter() - started) * 1000
                async with database.session_factory()() as db:
                    await usage.record_tts(
                        db,
                        user_id=None,
                        provider=provider.name,
                        model=provider.model,
                        chars=len(item.text),
                    )
            parts.append(chunk)
    except TtsError as exc:
        return b"", ttfa, (time.perf_counter() - started) * 1000, f"{exc.code}: {exc.detail[:120]}"
    return b"".join(parts), ttfa, (time.perf_counter() - started) * 1000, ""


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def write_report(
    out: Path, results: list[Result], mapping: dict[str, str], settings: Settings
) -> str:
    lines = [
        f"# TTS benchmark — {out.name}",
        "",
        "Measured from this machine. TTFA = time to first audio byte (warm connection).",
        "",
        "| Provider | Lang | Voice | n | TTFA p50 (ms) | TTFA p90 (ms) | Total p50 (ms) | Errors |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for provider in mapping.values():
        for lang in LANGS:
            rows = [r for r in results if r.provider == provider and r.lang == lang]
            if not rows:
                continue
            ok = [r for r in rows if not r.error and r.ttfa_ms is not None]
            ttfa = [r.ttfa_ms for r in ok if r.ttfa_ms is not None]
            total = [r.total_ms for r in ok if r.total_ms is not None]
            voice = settings.tts_voices(provider, lang)[0].label  # type: ignore[arg-type]
            if ttfa:
                lines.append(
                    f"| {provider} | {lang} | {voice} | {len(ok)} | {statistics.median(ttfa):.0f} "
                    f"| {pct(ttfa, 0.9):.0f} | {statistics.median(total):.0f} "
                    f"| {len(rows) - len(ok)} |"
                )
            else:
                lines.append(f"| {provider} | {lang} | {voice} | 0 | — | — | — | {len(rows)} |")
    lines += ["", "## Characters used", ""]
    for provider in mapping.values():
        chars = sum(r.chars for r in results if r.provider == provider and r.ttfa_ms is not None)
        lines.append(f"- {provider}: {chars}")
    errors = [r for r in results if r.error]
    if errors:
        lines += ["", "## Errors (first 10)", ""]
        lines += [f"- {r.provider} {r.item_id} run {r.run}: {r.error}" for r in errors[:10]]
    report = "\n".join(lines) + "\n"
    (out / "report.md").write_text(report, encoding="utf-8")
    return report


def write_csv(out: Path, results: list[Result]) -> None:
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "provider",
                "lang",
                "item",
                "kind",
                "run",
                "chars",
                "ttfa_ms",
                "total_ms",
                "audio_s",
                "error",
            ]
        )
        for r in results:
            writer.writerow(
                [
                    r.provider,
                    r.lang,
                    r.item_id,
                    r.kind,
                    r.run,
                    r.chars,
                    f"{r.ttfa_ms:.0f}" if r.ttfa_ms is not None else "",
                    f"{r.total_ms:.0f}" if r.total_ms is not None else "",
                    r.audio_s if r.audio_s is not None else "",
                    r.error,
                ]
            )


def write_html(
    out: Path, items: list[Item], files: dict[tuple[str, str], str], mapping: dict[str, str]
) -> None:
    letters = sorted(mapping)
    rows = []
    for item in items:
        cells = []
        for letter in letters:
            path = files.get((mapping[letter], item.id))
            cells.append(
                f'<td><audio controls preload="none" src="{html.escape(path)}"></audio></td>'
                if path
                else "<td>—</td>"
            )
        rows.append(
            f"<tr><td>{item.lang}</td><td>{html.escape(item.text)}</td>{''.join(cells)}</tr>"
        )
    head = "".join(f"<th>{letter}</th>" for letter in letters)
    reveal = "".join(f"<li>{letter} = {html.escape(p)}</li>" for letter, p in mapping.items())
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>TTS blind test</title>
<style>body{{font-family:system-ui,sans-serif;margin:16px;max-width:1100px}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:6px;
text-align:left;vertical-align:middle}}audio{{width:220px}}</style></head><body>
<h1>TTS blind test</h1><p>Listen to each sentence and note which letter sounds more natural and
pronounces it better. Then open the answer at the bottom.</p>
<table><tr><th>Lang</th><th>Text</th>{head}</tr>{"".join(rows)}</table>
<details><summary>Show which provider is which</summary><ul>{reveal}</ul></details>
</body></html>"""
    (out / "index.html").write_text(page, encoding="utf-8")


def confirm() -> bool:
    return input("Continue? [y/N] ").strip().lower() in ("y", "yes", "s", "sim")


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    wanted = [p.strip() for p in args.providers.split(",") if p.strip()]
    names: list[TtsProviderName] = [
        p for p in PROVIDERS if p in wanted and settings.tts_provider_configured(p)
    ]
    for p in wanted:
        if p not in names:
            print(f"Skipping {p}: not configured (no credentials) or unknown.")
    if not names:
        print("No provider configured. Fill the TTS credentials in .env.")
        return 1
    items = load_corpus()
    if args.limit > 0:  # smoke test: first N items per language
        items = [i for lang in LANGS for i in [x for x in items if x.lang == lang][: args.limit]]
    per_run = sum(len(i.text) for i in items)
    warmup = sum(len(next(i for i in items if i.lang == lang).text) for lang in LANGS)
    planned = per_run * args.runs + warmup
    print(f"Items: {len(items)} | runs: {args.runs} | providers: {', '.join(names)}")
    for name in names:
        print(f"  {name}: ~{planned} characters")
    print("These come out of each provider's monthly free allowance.")
    if not args.yes and not await asyncio.to_thread(confirm):
        print("Cancelled.")
        return 1

    database.init_engine(settings.database_url)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = Path(args.out) / stamp
    shuffled = list(names)
    random.shuffle(shuffled)
    mapping = {chr(ord("A") + i): name for i, name in enumerate(shuffled)}
    results: list[Result] = []
    files: dict[tuple[str, str], str] = {}

    for name in names:
        provider = build_provider(settings, name)
        for lang in LANGS:
            voice = settings.tts_voices(name, lang)[0].id
            lang_items = [i for i in items if i.lang == lang]
            # Warm-up: opens the connection like a running server would.
            _, _, _, err = await synthesize(provider, lang_items[0], voice)
            if err:
                print(f"{name} {lang}: warm-up failed ({err}); skipping.")
                results += [
                    Result(name, lang, i.id, i.kind, 0, len(i.text), None, None, None, err)
                    for i in lang_items
                ]
                continue
            for run_no in range(1, args.runs + 1):
                for item in lang_items:
                    audio, ttfa, total, err = await synthesize(provider, item, voice)
                    seconds = None
                    if audio and run_no == 1:
                        rel = f"audio/{name}/{lang}/{item.id}.{extension(provider.mime)}"
                        (out / rel).parent.mkdir(parents=True, exist_ok=True)
                        (out / rel).write_bytes(audio)
                        files[(name, item.id)] = rel
                        seconds = audio_seconds(audio)
                    results.append(
                        Result(
                            name,
                            lang,
                            item.id,
                            item.kind,
                            run_no,
                            len(item.text),
                            ttfa,
                            total,
                            seconds,
                            err,
                        )
                    )
                print(f"{name} {lang} run {run_no}/{args.runs} done")

    out.mkdir(parents=True, exist_ok=True)
    write_csv(out, results)
    write_html(out, items, files, mapping)
    print()
    print(write_report(out, results, mapping, settings))
    print(f"Saved to {out}")
    print(f"Blind test: {out / 'index.html'}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--providers", default=",".join(PROVIDERS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=0, help="items per language (smoke test)")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
