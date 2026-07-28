"""Hosted scheduler helpers (no network)."""

from hosted import authorize_cron, shadow_from_env, submit_from_env


def test_shadow_defaults_true_when_unset(monkeypatch):
    monkeypatch.delenv("BOT_SHADOW_MODE", raising=False)
    assert shadow_from_env() is True


def test_shadow_defaults_true_when_blank(monkeypatch):
    monkeypatch.setenv("BOT_SHADOW_MODE", "")
    assert shadow_from_env() is True


def test_submit_defaults_false(monkeypatch):
    monkeypatch.delenv("BOT_SUBMIT", raising=False)
    assert submit_from_env() is False
    monkeypatch.setenv("BOT_SUBMIT", "")
    assert submit_from_env() is False


def test_authorize_cron_bearer(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    assert authorize_cron({"Authorization": "Bearer s3cret"}) is True
    assert authorize_cron({"Authorization": "Bearer wrong"}) is False
    assert authorize_cron({}) is False


def test_authorize_cron_fail_closed_without_secret(monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("HOSTED_RUN_SECRET", raising=False)
    monkeypatch.delenv("ALLOW_UNAUTH_CRON", raising=False)
    assert authorize_cron({"Authorization": "Bearer x"}) is False
