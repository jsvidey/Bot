
import os
import asyncpg

_pool=None

async def get_pool():
    global _pool
    if _pool is None:
        if not os.getenv("DATABASE_URL"):
            raise RuntimeError("DATABASE_URL belum diatur")
        _pool=await asyncpg.create_pool(os.getenv("DATABASE_URL"),min_size=1,max_size=10,statement_cache_size=0,ssl="require")
    return _pool

async def close_db():
    global _pool
    if _pool:
        await _pool.close(); _pool=None

async def init_db():
    p=await get_pool()
    # Rename the legacy internal table for manual QR purchase approvals without losing rows.
    await p.execute("""DO $$ BEGIN
      IF to_regclass('public.manual_deposits') IS NOT NULL
         AND to_regclass('public.manual_payments') IS NULL THEN
        ALTER TABLE public.manual_deposits RENAME TO manual_payments;
      END IF;
    END $$;""")
    await p.execute("""
    -- Bootstrap the core schema before any ALTER/CREATE statements below.
    -- This allows a fresh PostgreSQL database to start without requiring a
    -- separately executed database.sql first; existing tables are preserved.
    CREATE TABLE IF NOT EXISTS users(
      user_id BIGINT PRIMARY KEY, username TEXT, full_name TEXT,
      total_unlocks BIGINT NOT NULL DEFAULT 0, is_admin BOOLEAN NOT NULL DEFAULT FALSE,
      vip BOOLEAN NOT NULL DEFAULT FALSE, vip_until TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      subscription_notice_at TIMESTAMPTZ
    );
    CREATE TABLE IF NOT EXISTS files(
      id BIGSERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL,
      owner_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
      title TEXT, media JSONB NOT NULL DEFAULT '[]'::jsonb, media_count INT NOT NULL DEFAULT 0,
      photo_count INT NOT NULL DEFAULT 0, video_count INT NOT NULL DEFAULT 0,
      document_count INT NOT NULL DEFAULT 0, audio_count INT NOT NULL DEFAULT 0,
      code_value_idr NUMERIC(18,2) NOT NULL DEFAULT 0, active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS purchases(
      id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
      purchase_type TEXT NOT NULL DEFAULT 'file', quantity NUMERIC(18,2) NOT NULL DEFAULT 0,
      amount BIGINT NOT NULL DEFAULT 0, provider TEXT NOT NULL DEFAULT 'manual',
      order_id TEXT UNIQUE NOT NULL, invoice_id TEXT UNIQUE, status TEXT NOT NULL DEFAULT 'pending',
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), paid_at TIMESTAMPTZ
    );
    CREATE TABLE IF NOT EXISTS unlock_transactions(
      id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
      code TEXT NOT NULL, payment_type TEXT NOT NULL DEFAULT 'qr',
      amount NUMERIC(18,2) NOT NULL DEFAULT 0,
      expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW()+INTERVAL '24 hours'),
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS manual_payments(
      id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
      amount NUMERIC(18,2) NOT NULL, proof_file_id TEXT, proof_type TEXT,
      target_code TEXT, target_type TEXT, quantity NUMERIC(18,2) DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'pending', admin_id BIGINT, note TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), processed_at TIMESTAMPTZ,
      qr_message_id BIGINT, proof_message_id BIGINT
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL DEFAULT '');
    INSERT INTO settings(key,value) VALUES
      ('payment_bayargg_enabled','on'),('payment_cashi_enabled','on'),
      ('payment_manual_enabled','on'),
      ('maintenance','off'),
      ('vip_code_delay_minutes','30'),('media_send_delay_ms','2000'),
      ('manual_qr_file_id',''),('preferred_b2_account','0'),('default_watermark_enabled','on')
    ON CONFLICT(key) DO NOTHING;

    CREATE TABLE IF NOT EXISTS vip_packages(
      code TEXT PRIMARY KEY, name TEXT NOT NULL, price BIGINT NOT NULL,
      duration_days INT NOT NULL DEFAULT 30, active BOOLEAN NOT NULL DEFAULT TRUE
    );
    INSERT INTO vip_packages(code,name,price,duration_days) VALUES
      ('vip1','VIP 1 • 30 Hari',100000,30),
      ('vip2','VIP 2 • 15 Hari',50000,15),
      ('vip3','VIP 3 • 7 Hari',35000,7),
      ('vip4','VIP 4 • 2 Hari',25000,2)
    ON CONFLICT(code) DO NOTHING;

    ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS banned BOOLEAN NOT NULL DEFAULT FALSE;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS can_unlock BOOLEAN NOT NULL DEFAULT TRUE;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS bot_started_at TIMESTAMPTZ;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_plan_days INT NOT NULL DEFAULT 0;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_daily_limit INT NOT NULL DEFAULT 0;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS language TEXT;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS pending_start_code TEXT;

    ALTER TABLE files ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];
    ALTER TABLE files ADD COLUMN IF NOT EXISTS price_idr NUMERIC(18,2) NOT NULL DEFAULT 0;
    ALTER TABLE files ADD COLUMN IF NOT EXISTS views BIGINT NOT NULL DEFAULT 0;
    ALTER TABLE files ADD COLUMN IF NOT EXISTS likes BIGINT NOT NULL DEFAULT 0;
    ALTER TABLE files ADD COLUMN IF NOT EXISTS hates BIGINT NOT NULL DEFAULT 0;
    ALTER TABLE files ADD COLUMN IF NOT EXISTS favorites BIGINT NOT NULL DEFAULT 0;
    -- New marketplace metadata. Additive migration keeps existing code/media intact.
    ALTER TABLE files ADD COLUMN IF NOT EXISTS review_code TEXT;
    ALTER TABLE files ADD COLUMN IF NOT EXISTS code_type TEXT NOT NULL DEFAULT 'media';
    ALTER TABLE files ADD COLUMN IF NOT EXISTS server_name TEXT NOT NULL DEFAULT 'Media Rare';
    ALTER TABLE files ADD COLUMN IF NOT EXISTS access_mode TEXT NOT NULL DEFAULT 'all';
    ALTER TABLE files ADD COLUMN IF NOT EXISTS auto_delete BOOLEAN NOT NULL DEFAULT FALSE;
    ALTER TABLE files ADD COLUMN IF NOT EXISTS allow_forward BOOLEAN NOT NULL DEFAULT TRUE;
    ALTER TABLE files ADD COLUMN IF NOT EXISTS watermark_enabled BOOLEAN NOT NULL DEFAULT TRUE;
    ALTER TABLE files ADD COLUMN IF NOT EXISTS review_media JSONB NOT NULL DEFAULT '[]'::jsonb;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_files_review_code_unique ON files(review_code) WHERE review_code IS NOT NULL;
    ALTER TABLE purchases ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
    ALTER TABLE purchases ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
    ALTER TABLE manual_payments ADD COLUMN IF NOT EXISTS qr_message_id BIGINT;
    ALTER TABLE manual_payments ADD COLUMN IF NOT EXISTS proof_message_id BIGINT;



    CREATE TABLE IF NOT EXISTS code_reactions(
      user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
      code TEXT NOT NULL REFERENCES files(code) ON DELETE CASCADE,
      reaction TEXT NOT NULL CHECK(reaction IN ('like','hate','favorite')),
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY(user_id,code,reaction)
    );

    CREATE TABLE IF NOT EXISTS delivery_messages(
      id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, chat_id BIGINT NOT NULL,
      message_id BIGINT NOT NULL, code TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
      UNIQUE(chat_id,message_id)
    );
    CREATE INDEX IF NOT EXISTS idx_delivery_expiry ON delivery_messages(expires_at);

    CREATE TABLE IF NOT EXISTS code_group_shares(
      id BIGSERIAL PRIMARY KEY, code TEXT NOT NULL, group_id BIGINT NOT NULL,
      shared_by BIGINT NOT NULL, first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(code,group_id)
    );

    CREATE TABLE IF NOT EXISTS code_cooldowns(
      user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
      code TEXT NOT NULL,
      opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY(user_id,code)
    );

    CREATE TABLE IF NOT EXISTS vip_daily_opens(
      user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
      open_date DATE NOT NULL DEFAULT CURRENT_DATE,
      used_count INT NOT NULL DEFAULT 0,
      PRIMARY KEY(user_id,open_date)
    );
    CREATE INDEX IF NOT EXISTS idx_vip_daily_opens_date ON vip_daily_opens(open_date);


    CREATE TABLE IF NOT EXISTS error_logs(
      id BIGSERIAL PRIMARY KEY,
      level TEXT NOT NULL DEFAULT 'ERROR',
      source TEXT,
      message TEXT NOT NULL,
      user_id BIGINT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS b2_storage_accounts(
      account_id INT PRIMARY KEY CHECK(account_id BETWEEN 1 AND 10),
      name TEXT NOT NULL DEFAULT '',
      endpoint TEXT NOT NULL,
      region TEXT NOT NULL,
      bucket TEXT NOT NULL,
      key_id TEXT NOT NULL,
      application_key TEXT NOT NULL,
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

        CREATE TABLE IF NOT EXISTS b2_storage_moves(
      id BIGSERIAL PRIMARY KEY,
      code TEXT,
      from_account INT,
      to_account INT,
      moved_count INT NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'pending',
      error TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      finished_at TIMESTAMPTZ
    );

    -- Existing deployments may have the old unlock payment constraint.
    ALTER TABLE IF EXISTS unlock_transactions DROP CONSTRAINT IF EXISTS unlock_transactions_payment_type_check;
    ALTER TABLE IF EXISTS unlock_transactions ADD CONSTRAINT unlock_transactions_payment_type_check CHECK(payment_type IN ('qr','admin')) NOT VALID;
    UPDATE settings SET value='2000' WHERE key='media_send_delay_ms' AND value='3000';

    -- Remove obsolete Supabase objects from older deployments.
    -- The Telegram bot writes purchases with BIGINT users.user_id directly.
    -- The legacy trigger calls a UUID/text comparison and aborts every payment
    -- insert before the QR can be returned. Transaction notifications are
    -- handled by utils.payments._transaction_post after successful finalization.
    DROP TRIGGER IF EXISTS trg_notify_purchase ON public.purchases;
    DROP POLICY IF EXISTS purchases_owner_admin ON public.purchases;

    CREATE INDEX IF NOT EXISTS idx_manual_payments_status ON manual_payments(status,created_at);
    CREATE INDEX IF NOT EXISTS idx_purchases_status_created ON purchases(status,created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_files_server_active ON files(server_name,active);
    CREATE INDEX IF NOT EXISTS idx_error_logs_created ON error_logs(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_code_reactions_code ON code_reactions(code);
    CREATE INDEX IF NOT EXISTS idx_files_tags ON files USING GIN(tags);
    """)
    await p.execute("""
    INSERT INTO users(user_id,is_admin)
    SELECT $1::BIGINT,TRUE
    WHERE $1::BIGINT <> 0
    ON CONFLICT(user_id) DO UPDATE SET is_admin=TRUE
    """, int(os.getenv("OWNER_ID","0") or 0))
    await p.fetchval("SELECT 1")

async def execute(q,*a): return await (await get_pool()).execute(q,*a)
async def fetch(q,*a): return await (await get_pool()).fetch(q,*a)
async def fetchrow(q,*a): return await (await get_pool()).fetchrow(q,*a)
async def fetchval(q,*a): return await (await get_pool()).fetchval(q,*a)
