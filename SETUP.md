# Cloud setup checklist (pre–Part B)

Created 2026-07-27. Secrets live in `.env` (gitignored), Vercel, and GitHub
Actions — never in this file.

## What exists

| Service | Resource | Status |
|---------|----------|--------|
| GitHub | [janzola-personal/paper-swing-bot](https://github.com/janzola-personal/paper-swing-bot) (public) | Done — secret scanning + push protection on |
| Supabase | Project `paper-swing-bot` (`yjcretwvrmiuzjmjzmmg`, `us-east-1`) | Done — `ACTIVE_HEALTHY`; CLI linked |
| Resend | API key named `paper-swing-bot` | Done — `NOTIFY_EMAIL_FROM=onboarding@resend.dev` (test sender). Optional: you already have verified `quinpick.com` if you prefer `bot@quinpick.com` later |
| Vercel | Project `paper-swing-bot` under `janzola-personals-projects` | Done — env vars set; **GitHub not connected yet** |
| Local `.env` | Alpaca + Supabase + Resend + bot flags | Done — `BOT_SHADOW_MODE=true`, `BOT_SUBMIT=false` |

## Env vars wired

Per `DEPLOY.md` / `.env.example`:

| Variable | Local `.env` | Vercel (prod/preview/dev) | GitHub Actions secrets |
|----------|:---:|:---:|:---:|
| `ALPACA_API_KEY_ID` | ✓ | ✓ | ✓ |
| `ALPACA_API_SECRET_KEY` | ✓ | ✓ | ✓ |
| `SUPABASE_URL` | ✓ | ✓ | ✓ |
| `SUPABASE_ANON_KEY` | ✓ | ✓ | ✓ |
| `SUPABASE_SERVICE_ROLE_KEY` | ✓ | ✓ | ✓ |
| `DATABASE_URL` | ✓ (Session pooler) | ✓ prod/preview | ✓ |
| `RESEND_API_KEY` | ✓ | ✓ | ✓ |
| `NOTIFY_EMAIL_TO` | ✓ (git user.email) | ✓ | ✓ |
| `NOTIFY_EMAIL_FROM` | ✓ (`onboarding@resend.dev`) | ✓ | ✓ |
| `BOT_SHADOW_MODE` | `true` | ✓ | ✓ |
| `BOT_SUBMIT` | `false` | ✓ | ✓ |
| `NEXT_PUBLIC_SUPABASE_URL` | ✓ | ✓ | n/a |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | ✓ | ✓ | n/a |

## You still need to do (manual, ~5 min)

### 1. `DATABASE_URL` (required before Part B DB migration)

1. Open [Supabase → paper-swing-bot → Project Settings → Database](https://supabase.com/dashboard/project/yjcretwvrmiuzjmjzmmg/settings/database).
2. Copy the **URI** connection string (reset DB password if you never saved it).
3. Host looks like: `db.yjcretwvrmiuzjmjzmmg.supabase.co`.
4. Put it in local `.env` as `DATABASE_URL=...`, then:

```bash
# Local
# edit .env

# Vercel (production + preview; development optional)
printf '%s' "$DATABASE_URL" | vercel env add DATABASE_URL production --yes --force --sensitive
printf '%s' "$DATABASE_URL" | vercel env add DATABASE_URL preview --yes --force --sensitive

# GitHub Actions
gh secret set DATABASE_URL -R janzola-personal/paper-swing-bot
```

### 2. Connect Vercel ↔ GitHub

`vercel git connect` failed (GitHub app / permissions). In the browser:

1. [Vercel → paper-swing-bot → Settings → Git](https://vercel.com/janzola-personals-projects/paper-swing-bot/settings/git)
2. Connect `janzola-personal/paper-swing-bot`
3. If prompted, install/authorize the Vercel GitHub App on that org/user

No deploy needed until Part C (Next.js). The project is ready to receive env + later code.

### 3. Confirm notify email

`NOTIFY_EMAIL_TO` was set from git `user.email` (`juancarlosanzola@gmail.com`).
If that is wrong, update `.env`, Vercel, and `gh secret set NOTIFY_EMAIL_TO`.

### 4. Supabase Auth user (Part C — not blocking Part B)

When you start the dashboard:

1. Auth → Users → invite/create your email + password
2. Disable public sign-ups (Auth → Providers → Email)

Migrations for `bot_state` / `runs` / `journal` / `equity_snapshots` land in **Part B**.

## Ready for Part B?

**Yes**, for B1 (broker verify) and engine hosting work. Pause only if you want
`DATABASE_URL` filled first before B3 (Postgres state).

Do **not** flip `BOT_SUBMIT` or leave shadow until Part D checklist.

## Quick URLs

- Repo: https://github.com/janzola-personal/paper-swing-bot
- Supabase: https://supabase.com/dashboard/project/yjcretwvrmiuzjmjzmmg
- Vercel: https://vercel.com/janzola-personals-projects/paper-swing-bot
- Playbook: `CURSOR_PROMPTS.md` Part B
