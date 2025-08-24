# Join Bot (Aiogram v2) — Render

## Quick start
1) Add these files to a GitHub repo (or upload the provided ZIP).
2) On Render: New > Background Worker > Connect the repo.
3) Set **Environment variable** `JOIN_TOKEN` to your Telegram bot token.
4) Build command: `pip install -r requirements.txt`
5) Start command: `python3 join_bot.py`
6) Deploy.

If the build fails because of `aiohttp`, make sure the version is `3.8.5` as pinned here.
