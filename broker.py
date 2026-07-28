"""
Alpaca wrapper (alpaca-py SDK). Paper trading is enforced three ways:

  1. config.PAPER_TRADING must be True (main.py refuses to start otherwise).
  2. TradingClient is constructed with paper=True unconditionally.
  3. After connecting we check the account number: Alpaca paper accounts
     start with "PA". If it doesn't, we abort before any order.

Verified against alpaca-py 0.43.x / official docs (2026-07-27):
  - paper=True: https://alpaca.markets/sdks/python/trading.html
  - get_account / get_all_positions / submit_order + MarketOrderRequest DAY:
    same page
  - get_clock: https://alpaca.markets/sdks/python/api_reference/trading/clock.html
  - DAY after close queues for next session:
    https://docs.alpaca.markets/docs/orders-at-alpaca
SDK still accepts submit_order(order_data=...); paper defaults to True in
0.43.x — we pass paper=True explicitly anyway (never rely on the default).

Transient timeouts/connection errors retry up to 3 times (alpaca_retry).
"""

import os
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest

import config
from alpaca_retry import call_with_retries


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

    def _call(self, fn, *args, label: str, **kwargs):
        return call_with_retries(fn, *args, label=label, **kwargs)

    def _assert_paper(self) -> None:
        acct = self._call(self.client.get_account, label="get_account")
        number = str(getattr(acct, "account_number", ""))
        if not number.startswith("PA"):
            raise SystemExit(
                f"Account {number!r} does not look like a paper account. "
                "Refusing to trade. Check your keys come from the Paper dashboard."
            )

    # ----- account -----------------------------------------------------
    def equity_and_cash(self) -> tuple[float, float]:
        acct = self._call(self.client.get_account, label="get_account")
        return float(acct.equity), float(acct.cash)

    def positions(self) -> dict[str, int]:
        """symbol -> signed share count (long-only system, so >= 0)."""
        out: dict[str, int] = {}
        for p in self._call(self.client.get_all_positions, label="get_all_positions"):
            out[p.symbol] = int(float(p.qty))
        return out

    def open_orders(self) -> list[dict[str, Any]]:
        """Open (unfilled) orders — used to journal reconcile warnings."""
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=100)
        rows = self._call(self.client.get_orders, filter=req, label="get_orders")
        out = []
        for o in rows or []:
            out.append(
                {
                    "id": str(getattr(o, "id", "")),
                    "symbol": getattr(o, "symbol", ""),
                    "qty": float(getattr(o, "qty", 0) or 0),
                    "filled_qty": float(getattr(o, "filled_qty", 0) or 0),
                    "side": str(getattr(o, "side", "")),
                    "status": str(getattr(o, "status", "")),
                }
            )
        return out

    def get_clock(self) -> Any:
        """Alpaca market clock (is_open, next_open, next_close, timestamp)."""
        return self._call(self.client.get_clock, label="get_clock")

    def market_open_now(self) -> bool:
        return bool(self.get_clock().is_open)

    # ----- orders ------------------------------------------------------
    def submit_market(self, symbol: str, qty: int, side: str) -> str:
        """Market order, time-in-force DAY.

        Intended usage: run the bot AFTER the close. Orders submitted while
        the market is closed queue and execute at the next open, which matches
        the backtest's next-open execution assumption.
        """
        if qty <= 0:
            raise ValueError("qty must be positive")
        order = self._call(
            self.client.submit_order,
            order_data=MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            ),
            label=f"submit_order:{symbol}",
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
