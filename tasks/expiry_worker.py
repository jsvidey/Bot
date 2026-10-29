import asyncio
import logging
from database import get_pool
from bot import bot

logger = logging.getLogger(__name__)

async def worker():
    while True:
        try:
            p = await get_pool()
            # Archive first, capture claimants, then delete live rows in one transaction.
            # ON DELETE CASCADE removes their personal My Code Discount entries.
            async with p.acquire() as conn:
                async with conn.transaction():
                    due = await conn.fetch("""
                        SELECT id, code,
                          CASE WHEN expires_at <= NOW() THEN 'expired' ELSE 'full' END AS reason
                        FROM discount_codes
                        WHERE expires_at <= NOW() OR used_count >= max_uses
                        ORDER BY id LIMIT 200
                        FOR UPDATE SKIP LOCKED
                    """)
                    notifications = []
                    for item in due:
                        people = await conn.fetch(
                            "SELECT user_id FROM user_discount_codes WHERE discount_id=$1",
                            item['id'],
                        )
                        notifications.extend({
                            'user_id': int(person['user_id']),
                            'code': item['code'],
                            'status': item['reason'],
                        } for person in people)
                        await conn.execute("""
                            INSERT INTO discount_code_archive(code,status)
                            VALUES($1,$2)
                            ON CONFLICT(code) DO UPDATE
                            SET status=EXCLUDED.status, archived_at=NOW()
                        """, item['code'], item['reason'])
                        await conn.execute("DELETE FROM discount_codes WHERE id=$1", item['id'])
            for row in notifications:
                if row['status'] == 'expired':
                    message = f"⌛ Code Discount {row['code']} sudah kedaluwarsa dan otomatis dihapus dari My Code Discount. Silakan redeem kode baru dari grup."
                else:
                    message = f"⛔ Code Discount {row['code']} sudah full/seluruh kuota penggunaannya terpakai dan otomatis dihapus dari My Code Discount. Silakan redeem kode lain dari grup."
                try:
                    await bot.send_message(row['user_id'], message)
                except Exception:
                    logger.info('Could not notify user %s about discount code cleanup', row['user_id'])
            await p.execute("DELETE FROM discount_code_archive WHERE archived_at < NOW()-INTERVAL '180 days'")
            rows = await p.fetch("DELETE FROM delivery_messages WHERE expires_at<=NOW() RETURNING chat_id,message_id")
            for r in rows:
                try:
                    await bot.delete_message(r['chat_id'], r['message_id'])
                except Exception:
                    pass
        except Exception:
            logger.exception('expiry worker')
        await asyncio.sleep(60)
