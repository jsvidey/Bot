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
 await get_pool(); await init_db(); await b2_pool.reload_from_db()
 try:
  await bot.set_my_commands([
   BotCommand(command="start", description="Mulai bot / Start bot"),
   BotCommand(command="mypurchases", description="Riwayat pembelian / My purchases"),
   BotCommand(command="codetop", description="Top 10 Code"),
   BotCommand(command="searchcode", description="Cari Code / Search Code"),
   BotCommand(command="setting", description="Pengaturan bahasa / Language settings"),
  ])
  await bot.set_my_commands([
   BotCommand(command="start", description="Start the bot"),
   BotCommand(command="mypurchases", description="View purchase history"),
   BotCommand(command="codetop", description="Top 10 codes"),
   BotCommand(command="searchcode", description="Search for a code"),
   BotCommand(command="setting", description="Language settings"),
  ], language_code="en")
 except Exception as e:
  logging.warning("Could not register bot commands: %s", e)
 p=await get_pool();
 try: ADMIN_IDS.update(set(int(r['user_id']) for r in await p.fetch('SELECT user_id FROM users WHERE is_admin=TRUE') if int(r['user_id'])!=0))
 except Exception: pass
 tasks=[asyncio.create_task(dp.start_polling(bot)),asyncio.create_task(payment_worker()),asyncio.create_task(expiry_worker()),asyncio.create_task(subscription_worker())]
 yield
 for t in tasks:t.cancel()
 await close_db(); await bot.session.close()
app=FastAPI(lifespan=lifespan); app.include_router(bayar); app.include_router(cashi)
@app.get('/')
async def root():return {'status':'running'}
@app.get('/health')
async def health():return {'status':'ok'}
