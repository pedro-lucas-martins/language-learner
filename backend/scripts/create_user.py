"""Create a learner and print their access token once.

Usage (from backend/):
    python -m scripts.create_user --name "Pedro" --native pt-BR --level A1
    python -m scripts.create_user --name "Ola" --native pl-PL --level B1

The direction follows from the native language: pt-BR learns pl-PL and vice versa.
"""

import argparse
import asyncio

from app.config import get_settings
from app.database import dispose_engine, init_engine, session_factory
from app.services.auth import create_user


async def _main(name: str, native: str, level: str) -> None:
    init_engine(get_settings().database_url)
    try:
        async with session_factory()() as db:
            user, token = await create_user(db, name=name, native_lang=native, level=level)
    finally:
        await dispose_engine()
    print(f"User created: {user.name} ({user.native_lang} → {user.target_lang}, {user.level})")
    print("Access token (shown only once — store it in a password manager):")
    print(token)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True)
    parser.add_argument("--native", required=True, choices=["pt-BR", "pl-PL"])
    parser.add_argument("--level", default="A1", choices=["A1", "A2", "B1", "B2", "C1"])
    args = parser.parse_args()
    asyncio.run(_main(args.name, args.native, args.level))


if __name__ == "__main__":
    main()
