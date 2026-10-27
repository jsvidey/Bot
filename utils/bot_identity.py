from config import BOT_USERNAME

async def get_bot_username() -> str:
    """Return the bot username configured in admin settings, falling back to env/config."""
    try:
        from database import get_pool
        value = await (await get_pool()).fetchval("SELECT value FROM settings WHERE key='bot_username'")
        value = str(value or '').strip().lstrip('@')
        if value:
            return value
    except Exception:
        pass
    return str(BOT_USERNAME or '').strip().lstrip('@')
