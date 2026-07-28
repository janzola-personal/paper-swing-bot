"""
Email notifications via Resend (NOTIFICATIONS.md).

Off when RESEND_API_KEY is unset. One retry on failure; never raises into the
trading path. Never log API keys or secrets.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

import trading_day as trading_day_mod

log = logging.getLogger("notify")

RESEND_URL = "https://api.resend.com/emails"


@dataclass
class DecisionLine:
    symbol: str
    action: str  # buy / sell / hold / flat / skip / halt
    qty: int
    ref_price: float
    reason: str


def _redact(text: str) -> str:
    """Strip anything that looks like a key before logging."""
    key = os.environ.get("RESEND_API_KEY") or ""
    out = text
    if key and key in out:
        out = out.replace(key, "[REDACTED]")
    for env_name in (
        "ALPACA_API_SECRET_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "DATABASE_URL",
        "CRON_SECRET",
    ):
        val = os.environ.get(env_name) or ""
        if val and val in out:
            out = out.replace(val, "[REDACTED]")
    return out


def configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY") and os.environ.get("NOTIFY_EMAIL_TO"))


def dashboard_url() -> str:
    return (
        os.environ.get("DASHBOARD_URL")
        or os.environ.get("NEXT_PUBLIC_APP_URL")
        or (f"https://{os.environ['VERCEL_URL']}" if os.environ.get("VERCEL_URL") else "")
        or "(dashboard URL unset)"
    )


def mode_label(mode: str) -> str:
    if mode == "submit":
        return "paper"
    if mode == "shadow":
        return "shadow"
    if mode == "dry_run":
        return "dry-run"
    return mode


def digest_subject(trading_day: date, decisions: list[DecisionLine]) -> str:
    for d in decisions:
        if d.action == "buy" and d.qty > 0:
            return f"Bot · BUY {d.qty} {d.symbol}"
        if d.action == "sell" and d.qty > 0:
            return f"Bot · SELL {d.qty} {d.symbol}"
    actions = {d.action for d in decisions if d.symbol != "*"}
    if actions and actions <= {"hold"}:
        return "Bot · HOLD ALL"
    if actions and actions <= {"flat", "hold"}:
        return "Bot · FLAT"
    return f"Bot · no trades · {trading_day.isoformat()}"


def build_digest_body(
    *,
    trading_day: date,
    mode: str,
    decisions: list[DecisionLine],
    equity: float,
    cash: float,
    day_pnl_pct: float | None,
    gate_line: str | None = None,
    first_submit: bool = False,
) -> str:
    now = trading_day_mod.now_et()
    lines = [
        f"Trading day {trading_day.isoformat()} · ran {now.strftime('%H:%M')} ET · {mode_label(mode)}",
        "",
    ]
    if first_submit and mode == "submit":
        lines.extend(
            [
                "  ★ FIRST PAPER SUBMIT — orders are real Alpaca PAPER market DAY orders.",
                "    Submitted after the close → they queue and fill at the next open.",
                "    (Still paper money — not live.)",
                "",
            ]
        )
    for d in decisions:
        if d.symbol == "*":
            continue
        if d.action in ("buy", "sell") and d.qty > 0:
            fill_note = (
                " → queues for tomorrow's open (DAY)"
                if mode == "submit"
                else (" → fills at tomorrow's open" if d.action == "buy" else " → next open")
            )
            lines.append(
                f"  {d.action.upper():4s} {d.qty} {d.symbol} @ ~{d.ref_price:.2f}{fill_note}"
            )
        else:
            lines.append(f"  {d.action.upper():5s} {d.symbol}")
        # Indent reason / inputs (strategy already embeds rsi/sma in reason)
        for part in d.reason.split(" | "):
            lines.append(f"       {part}")
        lines.append("")
    pnl = ""
    if day_pnl_pct is not None:
        pnl = f"  ({day_pnl_pct:+.2%} today)"
    lines.append(f"  Equity ${equity:,.2f}{pnl}   Cash ${cash:,.2f}")
    if gate_line:
        lines.append(f"  {gate_line}")
    elif mode == "submit":
        lines.append("  Gate: Stage B paper (counters update after this run)")
    else:
        lines.append("  Gate: not in Stage B paper yet")
    lines.append("")
    lines.append(f"  → {dashboard_url()}")
    return "\n".join(lines)


def build_halt_body(
    *,
    trading_day: date,
    reason: str,
    equity: float,
    peak: float,
    flatten_lines: list[str],
) -> str:
    short = reason[:80]
    lines = [
        f"Trading day {trading_day.isoformat()}",
        f"HALT: {reason}",
        f"Equity ${equity:,.2f} vs peak ${peak:,.2f}",
        "",
        "Flatten actions:",
    ]
    if flatten_lines:
        lines.extend(f"  {x}" for x in flatten_lines)
    else:
        lines.append("  (none recorded)")
    lines.extend(
        [
            "",
            "Hard drawdown halt needs dashboard reset-halt after you review the journal.",
            f"→ {dashboard_url()}",
            f"(short: {short})",
        ]
    )
    return "\n".join(lines)


def build_error_body(*, trading_day: date | None, error_class: str, detail: str) -> str:
    day = trading_day.isoformat() if trading_day else "unknown"
    return "\n".join(
        [
            f"Trading day {day}",
            f"Error class: {error_class}",
            f"Detail: {detail[:300]}",
            "",
            "If design holds, no partial orders were submitted before the failure.",
            "runs.status should be 'error'. Check scheduler logs (stack traces stay there).",
            f"→ {dashboard_url()}",
        ]
    )


def build_norun_body(*, trading_day: date, detail: str) -> str:
    return "\n".join(
        [
            f"No successful run recorded for trading day {trading_day.isoformat()}.",
            f"Detail: {detail}",
            "",
            "Possible causes: both schedulers failed, holiday misconfiguration, broken deploy.",
            "This is the most important alert — silence means you might think the bot traded when it did not.",
            f"→ {dashboard_url()}",
        ]
    )


def send_email(
    subject: str,
    body: str,
    *,
    post: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Send via Resend. Returns status string. Never raises. One retry."""
    if not configured():
        return "skipped_unconfigured"
    api_key = os.environ["RESEND_API_KEY"]
    to_addr = os.environ["NOTIFY_EMAIL_TO"]
    from_addr = os.environ.get("NOTIFY_EMAIL_FROM") or "onboarding@resend.dev"
    payload = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "text": body,
    }
    data = json.dumps(payload).encode("utf-8")

    def _do_post() -> tuple[int, str]:
        if post is not None:
            return post(RESEND_URL, data, api_key)
        req = urllib.request.Request(
            RESEND_URL,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")[:200]
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", "replace")[:200]
            return e.code, err_body
        except Exception as exc:  # noqa: BLE001
            return 0, type(exc).__name__

    status, resp_text = _do_post()
    if 200 <= status < 300:
        log.info("notify sent subject=%s status=%s", subject, status)
        return f"sent:{status}"

    log.warning(
        "notify attempt1 failed subject=%s status=%s body=%s",
        subject,
        status,
        _redact(resp_text),
    )
    sleep(0.5)
    status2, resp_text2 = _do_post()
    if 200 <= status2 < 300:
        log.info("notify sent on retry subject=%s status=%s", subject, status2)
        return f"sent_retry:{status2}"
    log.error(
        "notify failed subject=%s status=%s body=%s",
        subject,
        status2,
        _redact(resp_text2),
    )
    return f"failed:{status2}"


def send_digest(
    *,
    trading_day: date,
    mode: str,
    decisions: list[DecisionLine],
    equity: float,
    cash: float,
    day_pnl_pct: float | None = None,
    gate_line: str | None = None,
    first_submit: bool = False,
    post: Callable[..., Any] | None = None,
) -> str:
    subject = digest_subject(trading_day, decisions)
    if first_submit and mode == "submit":
        subject = f"Bot · FIRST SUBMIT · {subject.removeprefix('Bot · ')}"
    body = build_digest_body(
        trading_day=trading_day,
        mode=mode,
        decisions=decisions,
        equity=equity,
        cash=cash,
        day_pnl_pct=day_pnl_pct,
        gate_line=gate_line,
        first_submit=first_submit,
    )
    return send_email(subject, body, post=post)


def send_halt(
    *,
    trading_day: date,
    reason: str,
    equity: float,
    peak: float,
    flatten_lines: list[str] | None = None,
    post: Callable[..., Any] | None = None,
) -> str:
    short = reason.split(";")[0].strip()[:60] or "risk halt"
    subject = f"Bot · HALT · {short}"
    body = build_halt_body(
        trading_day=trading_day,
        reason=reason,
        equity=equity,
        peak=peak,
        flatten_lines=flatten_lines or [],
    )
    return send_email(subject, body, post=post)


def send_error(
    *,
    trading_day: date | None,
    error_class: str,
    detail: str,
    post: Callable[..., Any] | None = None,
) -> str:
    subject = "Bot · ERROR · run failed"
    body = build_error_body(
        trading_day=trading_day, error_class=error_class, detail=detail
    )
    return send_email(subject, body, post=post)


def send_norun(
    *,
    trading_day: date,
    detail: str,
    post: Callable[..., Any] | None = None,
) -> str:
    subject = f"Bot · NO RUN · {trading_day.isoformat()}"
    body = build_norun_body(trading_day=trading_day, detail=detail)
    return send_email(subject, body, post=post)
