/** Server-only Alpaca paper REST helpers (keys never sent to browser). */

const BASE = "https://paper-api.alpaca.markets";

function headers(): HeadersInit {
  const key = process.env.ALPACA_API_KEY_ID;
  const secret = process.env.ALPACA_API_SECRET_KEY;
  if (!key || !secret) {
    throw new Error("Missing ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY");
  }
  return {
    "APCA-API-KEY-ID": key,
    "APCA-API-SECRET-KEY": secret,
  };
}

export type AlpacaAccount = {
  equity: number;
  cash: number;
  account_number: string;
};

export type AlpacaPosition = {
  symbol: string;
  qty: number;
  avg_entry_price: number;
  current_price: number;
  unrealized_pl: number;
  unrealized_plpc: number;
};

export async function fetchAccount(): Promise<AlpacaAccount> {
  const res = await fetch(`${BASE}/v2/account`, {
    headers: headers(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`alpaca account ${res.status}`);
  const j = (await res.json()) as Record<string, string>;
  const number = String(j.account_number || "");
  if (!number.startsWith("PA")) {
    throw new Error("Account does not look like paper (PA…)");
  }
  return {
    equity: Number(j.equity),
    cash: Number(j.cash),
    account_number: number,
  };
}

export async function fetchPositions(): Promise<AlpacaPosition[]> {
  const res = await fetch(`${BASE}/v2/positions`, {
    headers: headers(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`alpaca positions ${res.status}`);
  const rows = (await res.json()) as Record<string, string>[];
  return rows.map((p) => ({
    symbol: p.symbol,
    qty: Number(p.qty),
    avg_entry_price: Number(p.avg_entry_price),
    current_price: Number(p.current_price),
    unrealized_pl: Number(p.unrealized_pl),
    unrealized_plpc: Number(p.unrealized_plpc),
  }));
}

export async function fetchClock(): Promise<{
  is_open: boolean;
  timestamp: string;
  next_open: string;
  next_close: string;
}> {
  const res = await fetch(`${BASE}/v2/clock`, {
    headers: headers(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`alpaca clock ${res.status}`);
  const j = (await res.json()) as Record<string, unknown>;
  return {
    is_open: Boolean(j.is_open),
    timestamp: String(j.timestamp || ""),
    next_open: String(j.next_open || ""),
    next_close: String(j.next_close || ""),
  };
}
