import runpy
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings import parse_admin_ids, parse_required_chats

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.py"
BASE_ENV = {
    "SECRET_KEY": "",
    "DEBUG": "",
    "ALLOWED_HOSTS": "",
    "CSRF_TRUSTED_ORIGINS": "",
    "ADMINS": "",
    "TELEGRAM_ADMINS": "",
    "REQUIRED_CHATS_JSON": "[]",
}


def load_settings(monkeypatch, **env: str) -> dict:
    for key, value in {**BASE_ENV, **env}.items():
        monkeypatch.setenv(key, value)
    return runpy.run_path(str(SETTINGS_PATH))


def test_debug_is_off_by_default(monkeypatch):
    settings = load_settings(monkeypatch, SECRET_KEY="x" * 50)
    assert settings["DEBUG"] is False
    assert settings["SESSION_COOKIE_SECURE"] is True
    assert settings["ALLOWED_HOSTS"] == []


def test_secret_key_required_in_production(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="SECRET_KEY"):
        load_settings(monkeypatch, SECRET_KEY="", DEBUG="False")


def test_debug_allows_dev_secret_key(monkeypatch):
    settings = load_settings(monkeypatch, SECRET_KEY="", DEBUG="true")
    assert settings["DEBUG"] is True
    assert settings["SECRET_KEY"].startswith("django-insecure")
    assert "localhost" in settings["ALLOWED_HOSTS"]


def test_hosts_and_csrf_origins_from_env(monkeypatch):
    settings = load_settings(
        monkeypatch,
        SECRET_KEY="x" * 50,
        ALLOWED_HOSTS="admin.example.com, localhost",
        CSRF_TRUSTED_ORIGINS="https://admin.example.com",
    )
    assert settings["ALLOWED_HOSTS"] == ["admin.example.com", "localhost"]
    assert settings["CSRF_TRUSTED_ORIGINS"] == ["https://admin.example.com"]


def test_parse_admin_ids():
    assert parse_admin_ids(" 1, 2,,3 ") == frozenset({1, 2, 3})
    assert parse_admin_ids("") == frozenset()
    with pytest.raises(ImproperlyConfigured):
        parse_admin_ids("1,abc")


def test_parse_required_chats_normalises_usernames():
    assert parse_required_chats('[[-100123, "mychannel"], [-100456, "@group"]]') == [
        (-100123, "@mychannel"),
        (-100456, "@group"),
    ]
    assert parse_required_chats("") == []


@pytest.mark.parametrize("raw", ["not json", '{"a": 1}', "[[1]]"])
def test_parse_required_chats_rejects_bad_config(raw):
    with pytest.raises(ImproperlyConfigured):
        parse_required_chats(raw)


def test_telegram_admins_do_not_clobber_django_admins(monkeypatch):
    settings = load_settings(monkeypatch, SECRET_KEY="x" * 50, TELEGRAM_ADMINS="11,22")
    assert settings["TELEGRAM_ADMINS"] == frozenset({11, 22})
    assert "ADMINS" not in settings  # Django's ADMINS keeps its default (list of 2-tuples)


def test_legacy_admins_env_var_still_supported(monkeypatch):
    settings = load_settings(monkeypatch, SECRET_KEY="x" * 50, ADMINS="33")
    assert settings["TELEGRAM_ADMINS"] == frozenset({33})
