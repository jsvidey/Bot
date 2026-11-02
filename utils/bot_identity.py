"""Resolve the active Telegram bot identity from the current BOT_TOKEN.

The username is never taken from an old database setting or a stale .env value.
It is refreshed from Telegram getMe whenever the application starts.
"""
from config import BOT_USERNAME as CONFIG_BOT_USERNAME

_ACTIVE_USERNAME = ""

async def refresh_bot_identity(bot):
    """Fetch the username belonging to the currently configured token."""
    global _ACTIVE_USERNAME
    me = await bot.get_me()
    _ACTIVE_USERNAME = str(me.username or "").strip().lstrip("@")
    if not _ACTIVE_USERNAME:
        raise RuntimeError("Telegram getMe did not return a bot username")
    # Keep legacy setting in sync for older modules/admin screens, but it is
    # informational only: get_bot_username never trusts this stored value.
    try:
        from database import get_pool
        await (await get_pool()).execute(
            """INSERT INTO settings(key,value) VALUES('bot_username',$1)
               ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value""",
            _ACTIVE_USERNAME,
        )
    except Exception:
        pass
    return _ACTIVE_USERNAME

async def get_bot_username() -> str:
    """Return the active bot username, not a previous bot's username."""
    if _ACTIVE_USERNAME:
        return _ACTIVE_USERNAME
    return str(CONFIG_BOT_USERNAME or "").strip().lstrip("@")
