"""PaperBroker paper checks and market-order request shape (mocked SDK)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from alpaca.trading.enums import OrderSide, TimeInForce

import broker
import config


def test_refuses_when_paper_trading_flag_false(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    with pytest.raises(SystemExit, match="PAPER_TRADING"):
        broker.PaperBroker()


def test_constructs_trading_client_with_paper_true(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", True)
    monkeypatch.setenv("ALPACA_API_KEY_ID", "PKTEST")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "SECRET")
    fake = MagicMock()
    fake.get_account.return_value = SimpleNamespace(account_number="PA123")
    with patch("broker.TradingClient", return_value=fake) as ctor:
        b = broker.PaperBroker()
    ctor.assert_called_once_with("PKTEST", "SECRET", paper=True)
    assert b.client is fake


def test_aborts_when_account_number_not_pa(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", True)
    monkeypatch.setenv("ALPACA_API_KEY_ID", "PKTEST")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "SECRET")
    fake = MagicMock()
    fake.get_account.return_value = SimpleNamespace(account_number="LIVE999")
    with patch("broker.TradingClient", return_value=fake):
        with pytest.raises(SystemExit, match="does not look like a paper"):
            broker.PaperBroker()


def test_submit_market_uses_day_tif(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", True)
    monkeypatch.setenv("ALPACA_API_KEY_ID", "PKTEST")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "SECRET")
    fake = MagicMock()
    fake.get_account.return_value = SimpleNamespace(account_number="PA123")
    fake.submit_order.return_value = SimpleNamespace(id="ord-1")
    with patch("broker.TradingClient", return_value=fake):
        b = broker.PaperBroker()
        oid = b.submit_market("SPY", 1, "buy")
    assert oid == "ord-1"
    kwargs = fake.submit_order.call_args.kwargs
    req = kwargs["order_data"]
    assert req.symbol == "SPY"
    assert req.qty == 1
    assert req.side == OrderSide.BUY
    assert req.time_in_force == TimeInForce.DAY
