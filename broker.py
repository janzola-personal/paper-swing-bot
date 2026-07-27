"""
Alpaca wrapper (alpaca-py SDK). Paper trading is enforced three ways:

  1. config.PAPER_TRADING must be True (main.py refuses to start otherwise).
  2. TradingClient is constructed with paper=True unconditionally.
  3. After connecting we check the account number: Alpaca paper accounts
     start with "PA". If it doesn't, we abort before any order.

NOTE: the alpaca-py API evolves. Cursor Prompt 3 in CURSOR_PROMPTS.md asks
Cursor to verify this file against the current docs before first use.
Docs: https://alpaca.markets/sdks/python/
"""

import os

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

import config


class PaperBroker:
    def __init__(self) -> None:
        if not config.PAPER_TRADING:
            raise SystemExit("config.PAPER_TRADING is False. Refusing to run. See README go-live checklist.")
        key = os.environ.get("ALPACA_API_KEY_ID")
        secret = os.environ.get("ALPACA_API_SECRET_KEY")
        if not key or not secret:
            raise SystemExit("Missing ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY in .env")
        self.client = TradingClient(key, secret, paper=True)
        self._assert_paper()

    def _assert_paper(self) -> None:
        acct = self.client.get_account()
        number = str(getattr(acct, "account_number", ""))
        if not number.startswith("PA"):
            raise SystemExit(
                f"Account {number!r} does not look like a paper account. "
                "Refusing to trade. Check your keys come from the Paper dashboard."
            )

    # ----- account -----------------------------------------------------
    def equity_and_cash(self) -> tuple[float, float]:
        acct = self.client.get_account()
        return float(acct.equity), float(acct.cash)

    def positions(self) -> dict[str, int]:
        """symbol -> signed share count (long-only system, so >= 0)."""
        out: dict[str, int] = {}
        for p in self.client.get_all_positions():
            out[p.symbol] = int(float(p.qty))
        return out

    def market_open_now(self) -> bool:
        return bool(self.client.get_clock().is_open)

    # ----- orders ------------------------------------------------------
    def submit_market(self, symbol: str, qty: int, side: str) -> str:
        """Market order, time-in-force DAY.

        Intended usage: run the bot AFTER the close. Orders submitted while
        the market is closed queue and execute at the next open, which matches
        the backtest's next-open execution assumption.
        """
        if qty <= 0:
            raise ValueError("qty must be positive")
        order = self.client.submit_order(
            MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
        )
        return str(order.id)

    def flatten_all(self, submit: bool) -> list[str]:
        """Sell every open position (next open). Returns human-readable lines."""
        lines = []
        for symbol, qty in self.positions().items():
            if qty > 0:
                if submit:
                    oid = self.submit_market(symbol, qty, "sell")
                    lines.append(f"SELL {qty} {symbol} (order {oid})")
                else:
                    lines.append(f"[dry-run] would SELL {qty} {symbol}")
        return lines
