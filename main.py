import asyncio,logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aiogram.types import BotCommand
from bot import bot,dp
from database import get_pool,close_db,init_db
from config import ADMIN_IDS
from utils.b2_storage import b2_pool
from api.bayargg_webhook import router as bayar
from api.cashi_webhook import router as cashi
from tasks.payment_worker import worker as payment_worker
from tasks.expiry_worker import worker as expiry_worker
from tasks.subscription_worker import worker as subscription_worker
logging.basicConfig(level=logging.INFO,format='%(asctime)s | %(levelname)s | %(message)s')
@asynccontextmanager
async def lifespan(app):
 # Fail loudly during startup when the deployment points to the wrong bot.
 await get_pool(); await init_db(); await b2_pool.reload_from_db()
 from utils.bot_identity import refresh_bot_identity
 active_username = await refresh_bot_identity(bot)
 expected_username = __import__("os").getenv("EXPECTED_BOT_USERNAME", "Boxcellbot").strip().lstrip("@")
 logging.info("Telegram token authenticated as @%s", active_username)
 if expected_username and active_username.lower() != expected_username.lower():
  raise RuntimeError(
   f"BOT_TOKEN belongs to @{active_username}, expected @{expected_username}. "
   "Update BOT_TOKEN in Railway Variables with the token from @BotFather for the new bot."
  )
 # A previous webhook prevents getUpdates polling (Telegram returns 409 Conflict).
 # Keep queued updates so the user's /start deep-link is not discarded.
 webhook = await bot.get_webhook_info()
 if webhook.url:
  logging.warning("Removing existing Telegram webhook before polling: %s", webhook.url)
 await bot.delete_webhook(drop_pending_updates=False)
 logging.info("Webhook cleared; starting polling for @%s", active_username)
 try:
  await bot.set_my_commands([
   BotCommand(command="start", description="Mulai / Start bot"),
   BotCommand(command="upload", description="Upload media (admin)"),
   BotCommand(command="vipbot", description="Paket VIP Bot / VIP Bot packages"),
   BotCommand(command="vip", description="Pilih akses VIP / Choose VIP access"),
   BotCommand(command="group", description="Link grup dan channel / Group and channel links"),
   BotCommand(command="code", description="Daftar Code / Browse Codes"),
   BotCommand(command="mypurchaces", description="Riwayat pembelian / My purchases"),
   BotCommand(command="codetop", description="Top 10 Code"),
   BotCommand(command="search", description="Cari Code / Search Code"),
   BotCommand(command="setting", description="Pengaturan bahasa / Language settings"),
  ])
  await bot.set_my_commands([
   BotCommand(command="start", description="Start the bot"),
   BotCommand(command="upload", description="Upload media (admin)"),
   BotCommand(command="vipbot", description="VIP Bot packages"),
   BotCommand(command="vip", description="Choose VIP access"),
   BotCommand(command="group", description="Group and channel links"),
   BotCommand(command="code", description="Browse all Codes"),
   BotCommand(command="mypurchaces", description="Purchase history"),
   BotCommand(command="codetop", description="Top 10 Codes"),
   BotCommand(command="search", description="Search for a Code"),
   BotCommand(command="setting", description="Language settings"),
  ], language_code="en")
 except Exception:
  logging.exception("Could not register bot commands")
 p=await get_pool()
 try:
  ADMIN_IDS.update(set(int(r['user_id']) for r in await p.fetch('SELECT user_id FROM users WHERE is_admin=TRUE') if int(r['user_id'])!=0))
 except Exception:
  logging.exception("Could not load database admins")

 async def run_polling():
  logging.info("Polling task is now active for @%s", active_username)
  await dp.start_polling(
   bot,
   allowed_updates=dp.resolve_used_update_types(),
   close_bot_session=False,
  )
  logging.error("Telegram polling stopped unexpectedly for @%s", active_username)

 def task_finished(task):
  if task.cancelled():
   return
  exc=task.exception()
  if exc:
   logging.critical("Background task %s crashed", task.get_name(), exc_info=(type(exc), exc, exc.__traceback__))

 tasks=[
  asyncio.create_task(run_polling(), name="telegram-polling"),
  asyncio.create_task(payment_worker(), name="payment-worker"),
  asyncio.create_task(expiry_worker(), name="expiry-worker"),
  asyncio.create_task(subscription_worker(), name="subscription-worker"),
 ]
 for task in tasks:
  task.add_done_callback(task_finished)
 try:
  yield
 finally:
  for task in tasks:
   task.cancel()
  await asyncio.gather(*tasks, return_exceptions=True)
  await close_db()
  await bot.session.close()

app=FastAPI(lifespan=lifespan); app.include_router(bayar); app.include_router(cashi)
@app.get('/')
async def root():return {'status':'running'}
@app.get('/health')
async def health():return {'status':'ok'}
