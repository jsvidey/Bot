
from decimal import Decimal
from datetime import datetime,timedelta,timezone
from database import get_pool

async def ensure_user(uid,username=None,name=None):
    p=await get_pool()
    await p.execute("""INSERT INTO users(user_id,username,full_name) VALUES($1,$2,$3)
    ON CONFLICT(user_id) DO UPDATE SET username=EXCLUDED.username,full_name=EXCLUDED.full_name,last_seen=NOW()""",uid,username,name)


async def is_vip(uid):
    p=await get_pool()
    return bool(await p.fetchval("SELECT vip AND (vip_until IS NULL OR vip_until>NOW()) FROM users WHERE user_id=$1",uid) or False)

async def vip_allowed(uid,code):
    if not await is_vip(uid): return True
    p=await get_pool()
    r=await p.fetchval("SELECT opened_at FROM code_cooldowns WHERE user_id=$1 AND code=$2",uid,code)
    if not r: return True
    try: minutes=int(await p.fetchval("SELECT value FROM settings WHERE key='vip_code_delay_minutes'") or 30)
    except: minutes=30
    return datetime.now(timezone.utc)-r.replace(tzinfo=timezone.utc) >= timedelta(minutes=minutes)

async def vip_daily_limit_for_days(days):
    """Daily code-open allowance for each VIP package duration."""
    mapping = {1:2, 3:4, 5:6, 7:7, 10:10, 15:15, 30:30}
    days=int(days or 0)
    if days in mapping:
        return mapping[days]
    # For future packages, use the package duration as the daily allowance,
    # with a minimum of 1. This keeps the rule deterministic without hardcoding
    # every possible package.
    return max(2, days)

async def vip_quota_status(conn, uid):
    user = await conn.fetchrow(
        "SELECT vip_plan_days,vip_daily_limit FROM users WHERE user_id=$1 FOR UPDATE", uid
    )
    limit = int(user["vip_daily_limit"] or 0) if user else 0
    if limit <= 0 and user:
        limit = await vip_daily_limit_for_days(int(user["vip_plan_days"] or 0))
    used = int(await conn.fetchval(
        "SELECT used_count FROM vip_daily_opens WHERE user_id=$1 AND open_date=CURRENT_DATE",
        uid
    ) or 0)
    return limit, used

async def unlock(uid,code,media_count,method):
    p=await get_pool()
    async with p.acquire() as c:
        async with c.transaction():
            f=await c.fetchrow("""
                SELECT owner_id,code_value_idr,price_idr,active
                FROM files WHERE lower(code)=lower($1) FOR UPDATE
            """,code)
            if not f or not f["active"]:
                return False,Decimal(0),"notfound",0

            user=await c.fetchrow("SELECT * FROM users WHERE user_id=$1 FOR UPDATE",uid)
            if not user or user["banned"] or not user["can_unlock"]:
                return False,Decimal(0),"blocked",0

            # The owner can always open their own code without spending anything.
            if int(f["owner_id"]) == int(uid):
                return True,Decimal(0),"own",0

            now=datetime.now(timezone.utc)
            vip=bool(user["vip"] and (user["vip_until"] is None or user["vip_until"]>now))
            if vip:
                limit, used = await vip_quota_status(c, uid)
                if limit > 0 and used >= limit:
                    return False,Decimal(0),"vip_quota",0

                await c.execute("""
                    INSERT INTO vip_daily_opens(user_id,open_date,used_count)
                    VALUES($1,CURRENT_DATE,1)
                    ON CONFLICT(user_id,open_date)
                    DO UPDATE SET used_count=vip_daily_opens.used_count+1
                """,uid)
                await c.execute("""
                    INSERT INTO code_cooldowns(user_id,code)
                    VALUES($1,$2)
                    ON CONFLICT(user_id,code) DO UPDATE SET opened_at=NOW()
                """,uid,code)
                await c.execute("UPDATE files SET views=views+1 WHERE code=$1",code)
                # Keep a 3-day access record so every delivered Telegram message
                # can be expired automatically and continuation can verify access.
                await c.execute("""
                    INSERT INTO unlock_transactions(user_id,code,payment_type,amount,expires_at)
                    VALUES($1,$2,'admin',0,NOW()+INTERVAL '3 days')
                """,uid,code)
                return True,Decimal(0),"vip",0

            # Re-opening an already unlocked code does not charge again while
            # its access window is still active.
            active = await c.fetchrow("""
                SELECT payment_type,expires_at
                FROM unlock_transactions
                WHERE user_id=$1 AND code=$2
                  AND payment_type IN ('qr','admin')
                  AND expires_at>NOW()
                ORDER BY expires_at DESC LIMIT 1
            """,uid,code)
            if active:
                # Existing wallet/QR access is still valid.
                # Do not charge again; the caller will proceed directly to delivery.
                return True,Decimal(0), "active", 0

            price=Decimal(str(f["price_idr"] or 0))
            # Wallet/balance payments have been removed. Paid Codes are purchased
            # through QR providers; VIP access is handled above.
            return False,Decimal(0),"invalid_method",Decimal(0)

