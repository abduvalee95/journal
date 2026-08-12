# Deploy runbook — Ustoz jurnali

Everything below runs on infrastructure this repository cannot reach: a VPS,
a Vercel project, and BotFather. The configuration files are committed
(`backend/Dockerfile`, `docker-compose.yml`, `Caddyfile`, `.env.example`);
these are the steps a person runs against them.

## 0. What runs where

| Piece | Where | Notes |
|---|---|---|
| FastAPI + bot + outbox worker | VPS, `app` container | single process, single worker |
| TLS / reverse proxy | VPS, `caddy` container | automatic Let's Encrypt |
| SQLite database | VPS, `./data/journal.db` | bind mount, survives rebuilds |
| Mini App (static) | Vercel | built from `miniapp/` |

The bot, the HTTP API and the outbox loop are one process. That is why the
Dockerfile pins `--workers 1`: a second worker would run a second outbox loop
and every student would receive their report twice.

## 1. VPS preparation

Hetzner CX22 or similar, Ubuntu 24.04:

```bash
apt update && apt upgrade -y
adduser deploy && usermod -aG sudo deploy
```

Disable password SSH — set `PasswordAuthentication no` in
`/etc/ssh/sshd_config`, then:

```bash
systemctl restart ssh
```

Firewall and Docker:

```bash
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
```

Point an A record for `api.<your-domain>` at the VPS IP **before** the first
`docker compose up`: Caddy requests a certificate on start and needs the name
to already resolve.

## 2. Configure

As `deploy`:

```bash
git clone <repo> ustoz-jurnali && cd ustoz-jurnali
cp .env.example .env
```

Fill in every blank in `.env`. Two of them are generated, not looked up:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # WEBHOOK_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # JWT_SECRET
```

`BASE_URL` must match the hostname in the `Caddyfile`, and `MINIAPP_URL` must
match the Vercel origin from step 5 — it is the allowed CORS origin, so a
wrong value makes every Mini App request fail in the browser.

Replace `api.domain.uz` in the `Caddyfile` with the real hostname.

The container runs as uid 10001, so give it the database directory:

```bash
mkdir -p data && sudo chown -R 10001:10001 data
```

## 3. Start

```bash
docker compose up -d --build
docker compose exec app alembic upgrade head
docker compose exec app python -m app.db.seed
```

The app registers its own Telegram webhook on startup from `BASE_URL` and
`WEBHOOK_SECRET` (see the `lifespan` handler in `backend/app/main.py`), so no
`setWebhook` call is needed. Confirm it took:

```bash
curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
curl https://api.<your-domain>/api/health     # {"status":"ok"}
```

If `getWebhookInfo` shows no URL, check `docker compose logs app` — the
lifespan logs the failure and continues rather than crashing.

## 4. Mini App on Vercel

New Project → this GitHub repo, then:

- Root Directory: `miniapp`
- Build Command: `npm run build`
- Output Directory: `dist`
- Environment variable: `VITE_API_URL=https://api.<your-domain>`

Deploy, copy the production URL, put it in `MINIAPP_URL` in the VPS `.env`,
and restart the backend so CORS picks it up:

```bash
docker compose up -d
```

Note that Vercel preview deployments get their own hostnames, which are not in
the allowed origins — previews cannot talk to production, by design.

Then in BotFather: `/newapp`, select the bot, set the Vercel URL as the Mini
App URL.

## 5. Daily backup

`crontab -e` as `deploy`. `.backup` is used rather than `cp` because it is safe
against a concurrent write:

```cron
0 22 * * * /usr/bin/docker compose -f /home/deploy/ustoz-jurnali/docker-compose.yml exec -T app python -c "import sqlite3;sqlite3.connect('data/journal.db').backup(sqlite3.connect('/tmp/backup.db'))" && /usr/bin/docker cp $(/usr/bin/docker compose -f /home/deploy/ustoz-jurnali/docker-compose.yml ps -q app):/tmp/backup.db /tmp/j-$(date +\%F).db && /usr/bin/rclone copy /tmp/j-$(date +\%F).db r2:journal-backups/ && rm /tmp/j-$(date +\%F).db
```

Simpler alternative, since the database is on a bind mount the host can read
directly (install `sqlite3` on the host first):

```cron
0 22 * * * sqlite3 /home/deploy/ustoz-jurnali/data/journal.db ".backup /tmp/j-$(date +\%F).db" && rclone copy /tmp/j-$(date +\%F).db r2:journal-backups/ && rm /tmp/j-$(date +\%F).db
```

Restore is a file copy with the stack stopped:

```bash
docker compose down
cp /path/to/backup.db data/journal.db && sudo chown 10001:10001 data/journal.db
docker compose up -d
```

## 6. Uptime monitoring

UptimeRobot → new HTTP monitor:

- URL: `https://api.<your-domain>/api/health`
- Interval: 5 minutes
- Alert: email

## 7. Production smoke test

In order, checking the effect of each before moving on:

1. Student sends `/start` to the bot and registers.
2. Teacher opens the Mini App — the student appears in today's roster.
3. Teacher fills attendance by hand and taps **Сақлаш** — that student
   receives their report within ~30s (the outbox polls on a 30s loop).
4. Teacher sends a voice note — the Mini App shows the spinner, then
   auto-fills within ~10-20s.
5. Teacher taps **Сақлаш** — every student receives a report.
6. Teacher opens the **Кеча** tab, changes a grade, taps **Сақлаш (жим)** —
   the grade changes and **no** new message is sent.

Step 6 is the one worth being deliberate about: it is the only check that the
correction path stays silent.

## Troubleshooting

**Every Mini App request fails with a CORS error.** `MINIAPP_URL` does not
match the origin the app is actually served from. It is set in one place only
— do not add CORS headers to the `Caddyfile`, because two sets of
`Access-Control-Allow-Origin` headers make browsers reject the response.

**Caddy will not get a certificate.** The A record must resolve to the VPS and
ports 80 and 443 must be open before the first start. `docker compose logs
caddy` names the failing challenge.

**Bot receives nothing.** `getWebhookInfo` shows `last_error_message`. A 403
there means `WEBHOOK_SECRET` in `.env` no longer matches what was registered;
restart the app container to re-register.

**Students get duplicate reports.** Something started a second app process —
check that `--workers 1` is still in the Dockerfile `CMD` and that only one
`app` container is running.
