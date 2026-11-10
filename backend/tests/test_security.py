import pytest

from app.config import Settings
from app.security import is_allowed_origin

PREVIEW = r"^https://language-learner(-[a-z0-9-]+)?\.vercel\.app$"


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "app_env": "production",
        "frontend_url": "https://language-learner.vercel.app",
        "vercel_preview_regex": PREVIEW,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "origin",
    [
        "https://language-learner.vercel.app",
        "https://language-learner.vercel.app/",
        "https://language-learner-git-feature-x-pedro.vercel.app",
    ],
)
def test_allows_own_origins(origin: str) -> None:
    assert is_allowed_origin(origin, make_settings())


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "",
        "https://someone-else.vercel.app",
        "https://language-learner.vercel.app.evil.com",
        "https://evil-language-learner.vercel.app",
        "http://language-learner.vercel.app",
        "http://localhost:5173",  # not allowed outside development
    ],
)
def test_rejects_other_origins(origin: str | None) -> None:
    assert not is_allowed_origin(origin, make_settings())


def test_localhost_allowed_in_development() -> None:
    settings = make_settings(app_env="development", frontend_url="http://localhost:5173")
    assert is_allowed_origin("http://localhost:5173", settings)


def test_no_preview_regex_means_exact_match_only() -> None:
    settings = make_settings(vercel_preview_regex="")
    assert not is_allowed_origin("https://language-learner-git-x.vercel.app", settings)


def test_malformed_voice_list_is_rejected() -> None:
    with pytest.raises(ValueError):
        make_settings(elevenlabs_voices_pl=":no-id")


def test_voice_pairs_are_parsed() -> None:
    settings = make_settings(elevenlabs_voices_pt="abc:Ana, def:Bruno")
    assert [(v.id, v.label) for v in settings.voices_pt] == [("abc", "Ana"), ("def", "Bruno")]
