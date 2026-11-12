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


def test_voice_pairs_are_parsed_per_provider_and_language() -> None:
    settings = make_settings(
        elevenlabs_voices_pt="abc:Ana, def:Bruno",
        google_tts_voices_pl="pl-PL-Chirp3-HD-Kore:Kasia",
        elevenlabs_voices_pl="uuid-1",
    )
    assert [(v.id, v.label) for v in settings.tts_voices("elevenlabs", "pt-BR")] == [
        ("abc", "Ana"),
        ("def", "Bruno"),
    ]
    assert [v.id for v in settings.tts_voices("google", "pl-PL")] == ["pl-PL-Chirp3-HD-Kore"]
    # A voice without a label uses its id as the label.
    assert settings.tts_voices("elevenlabs", "pl-PL")[0].label == "uuid-1"
    assert settings.tts_voices("google", "pt-BR") == []


def test_tts_provider_configured_checks_credentials() -> None:
    settings = make_settings(elevenlabs_api_key="key")
    assert settings.tts_provider_configured("elevenlabs")
    assert not settings.tts_provider_configured("google")


def test_unknown_tts_provider_is_rejected() -> None:
    with pytest.raises(ValueError):
        make_settings(tts_provider="polly")


def test_dev_extra_origins_only_in_development() -> None:
    from app.security import is_allowed_origin

    dev = make_settings(app_env="development", dev_extra_origins="https://192.168.0.10:5173/")
    prod = make_settings(app_env="production", dev_extra_origins="https://192.168.0.10:5173")
    assert is_allowed_origin("https://192.168.0.10:5173", dev)
    assert not is_allowed_origin("https://192.168.0.11:5173", dev)
    assert not is_allowed_origin("https://192.168.0.10:5173", prod)
