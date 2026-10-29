
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
      ('bot_username','JsShowfileebot'),
      ('maintenance','off'),
      ('vip_code_delay_minutes','30'),('vvip_code_delay_minutes','15'),('media_send_delay_ms','2000'),('vip_media_send_delay_ms','2000'),('vvip_media_send_delay_ms','1000'),
      ('manual_qr_file_id',''),('preferred_b2_account','0'),('default_watermark_enabled','on'),('watermark_text',''),('admin_chat_enabled','on'),('vip_channels_json',''),('vip_updates_url','https://t.me/+ezE2-f-YtEo4NzU1')
    ON CONFLICT(key) DO NOTHING;

    CREATE TABLE IF NOT EXISTS server_categories(
      server_no INT PRIMARY KEY CHECK(server_no BETWEEN 1 AND 10),
      name TEXT NOT NULL,
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    INSERT INTO server_categories(server_no,name,enabled) VALUES
      (1,'Media 5th ke bawah',TRUE),(2,'Media SMP',TRUE),(3,'Tante/Janda/STW',TRUE),
      (4,'Server 4',TRUE),(5,'Server 5',TRUE),(6,'Server 6',TRUE),(7,'OmeTV',TRUE),
      (8,'Server 8',TRUE),(9,'Server 9',TRUE),(10,'Server 10',TRUE)
    ON CONFLICT(server_no) DO NOTHING;

    CREATE TABLE IF NOT EXISTS vip_packages(
      code TEXT PRIMARY KEY, name TEXT NOT NULL, price BIGINT NOT NULL,
      duration_days INT NOT NULL DEFAULT 30, active BOOLEAN NOT NULL DEFAULT TRUE, link_url TEXT NOT NULL DEFAULT ''
    );
    INSERT INTO vip_packages(code,name,price,duration_days) VALUES
      ('vip1','VIP 1 • 30 Hari',100000,30),
      ('vip2','VIP 2 • 15 Hari',50000,15),
      ('vip3','VIP 3 • 7 Hari',35000,7),
      ('vip4','VIP 4 • 2 Hari',25000,2)
    ON CONFLICT(code) DO NOTHING;
    ALTER TABLE vip_packages ADD COLUMN IF NOT EXISTS link_url TEXT NOT NULL DEFAULT '';
    ALTER TABLE vip_packages ADD COLUMN IF NOT EXISTS tier TEXT NOT NULL DEFAULT 'vip';
    ALTER TABLE vip_packages ADD COLUMN IF NOT EXISTS daily_limit INT NOT NULL DEFAULT 2;
    UPDATE vip_packages SET tier='vip' WHERE tier IS NULL OR tier NOT IN ('vip','vvip');

    CREATE TABLE IF NOT EXISTS vip_group_packages(
      code TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      price BIGINT NOT NULL CHECK(price >= 1000),
      active BOOLEAN NOT NULL DEFAULT TRUE,
      link_url TEXT NOT NULL DEFAULT '',
      description TEXT NOT NULL DEFAULT 'Dapatkan akses instan ke konten premium dan eksklusif setelah pembayaran berhasil.',
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    ALTER TABLE vip_group_packages ADD COLUMN IF NOT EXISTS chat_id BIGINT;
    ALTER TABLE vip_group_packages ADD COLUMN IF NOT EXISTS success_message TEXT NOT NULL DEFAULT '✅ Berhasil masuk grup {group}! Terima kasih telah bergabung.';
    CREATE TABLE IF NOT EXISTS vip_group_invites(
      invite_link TEXT PRIMARY KEY,
      telegram_user_id BIGINT NOT NULL,
      chat_id BIGINT NOT NULL,
      package_code TEXT NOT NULL DEFAULT '',
      package_name TEXT NOT NULL DEFAULT 'VIP Group',
      link_chat_id BIGINT NOT NULL,
      link_message_id BIGINT NOT NULL,
      success_message TEXT NOT NULL DEFAULT '✅ Berhasil masuk grup {group}! Terima kasih telah bergabung.',
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      joined_at TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_vip_group_invites_user ON vip_group_invites(telegram_user_id);
    CREATE INDEX IF NOT EXISTS idx_vip_group_invites_chat ON vip_group_invites(chat_id);
    -- Migrate the three group packages that older versions stored in vip_packages.
    INSERT INTO vip_group_packages(code,name,price,active,link_url)
      SELECT code,
             CASE WHEN code='vip_bowceill' THEN 'VIP BOWCIEL'
                  WHEN code='vip_vgk' THEN 'VIP VGK'
                  WHEN code='premium_access' THEN 'PREMIUM ACCESS'
                  ELSE name END,
             CASE WHEN code='premium_access' AND price=100000 THEN 250000 ELSE price END,
             active,link_url
      FROM vip_packages WHERE code IN ('vip_bowceill','vip_vgk','premium_access')
    ON CONFLICT(code) DO NOTHING;
    INSERT INTO vip_group_packages(code,name,price,active,link_url)
      SELECT defaults.code,defaults.name,defaults.price,TRUE,''
      FROM (VALUES
        ('vip_bowciel','VIP BOWCIEL',50000::BIGINT),
        ('vip_vgk','VIP VGK',50000::BIGINT),
        ('premium_access','PREMIUM ACCESS',250000::BIGINT)
      ) AS defaults(code,name,price)
      WHERE NOT EXISTS (SELECT 1 FROM settings WHERE key='vip_group_packages_seeded')
    ON CONFLICT(code) DO NOTHING;
    INSERT INTO settings(key,value) VALUES('vip_group_packages_seeded','on') ON CONFLICT(key) DO NOTHING;
    UPDATE vip_group_packages SET link_url=COALESCE(NULLIF(link_url,''),(SELECT link_url FROM vip_packages WHERE code='vip_bowceill'),'')
      WHERE code='vip_bowciel';
    DELETE FROM vip_group_packages WHERE code='vip_bowceill';
    DELETE FROM vip_packages WHERE code IN ('vip_bowceill','vip_vgk','premium_access');
    INSERT INTO vip_packages(code,name,price,duration_days,active,link_url)
      VALUES('vipbot_1day','VIP Bot 1 Hari',25000,1,TRUE,'')
    ON CONFLICT(code) DO UPDATE SET name=EXCLUDED.name,price=EXCLUDED.price,duration_days=EXCLUDED.duration_days;
    -- Activate all five VIP Bot packages once. Later admin enable/disable choices are preserved.
    INSERT INTO settings(key,value) VALUES('vipbot_all_packages_activated_v1','pending') ON CONFLICT(key) DO NOTHING;
    UPDATE vip_packages SET active=TRUE
      WHERE code IN ('vip1','vip2','vip3','vip4','vipbot_1day')
        AND (SELECT value FROM settings WHERE key='vipbot_all_packages_activated_v1')='pending';
    UPDATE settings SET value='done' WHERE key='vipbot_all_packages_activated_v1' AND value='pending';
    -- Seed the VIP/VVIP Bot catalog once. Admin changes are preserved on later starts.
    INSERT INTO settings(key,value) VALUES('vipbot_vip_vvip_seed_v1','pending') ON CONFLICT(key) DO NOTHING;
    UPDATE vip_packages SET active=FALSE
      WHERE (SELECT value FROM settings WHERE key='vipbot_vip_vvip_seed_v1')='pending';
    INSERT INTO vip_packages(code,name,price,duration_days,active,link_url,tier,daily_limit)
    SELECT defaults.code,defaults.name,defaults.price,defaults.duration_days,TRUE,'',defaults.tier,defaults.daily_limit
    FROM (VALUES
      ('vip_1d','VIP 1 Hari',15000,1,'vip',2),
      ('vip_4d','VIP 4 Hari',30000,4,'vip',3),
      ('vip_7d','VIP 7 Hari',50000,7,'vip',4),
      ('vip_15d','VIP 15 Hari',55000,15,'vip',5),
      ('vvip_1d','VVIP 1 Hari',20000,1,'vvip',3),
      ('vvip_4d','VVIP 4 Hari',40000,4,'vvip',5),
      ('vvip_7d','VVIP 7 Hari',60000,7,'vvip',8),
      ('vvip_15d','VVIP 15 Hari',75000,15,'vvip',10)
    ) AS defaults(code,name,price,duration_days,tier,daily_limit)
    WHERE (SELECT value FROM settings WHERE key='vipbot_vip_vvip_seed_v1')='pending'
    ON CONFLICT(code) DO NOTHING;
    UPDATE settings SET value='done' WHERE key='vipbot_vip_vvip_seed_v1' AND value='pending';

    ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS banned BOOLEAN NOT NULL DEFAULT FALSE;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS can_unlock BOOLEAN NOT NULL DEFAULT TRUE;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS bot_started_at TIMESTAMPTZ;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_plan_days INT NOT NULL DEFAULT 0;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_daily_limit INT NOT NULL DEFAULT 0;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_tier TEXT NOT NULL DEFAULT 'vip';
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
    await p.execute("""
    CREATE TABLE IF NOT EXISTS discount_codes(
      id BIGSERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL,
      discount_type TEXT NOT NULL CHECK(discount_type IN ('percent','fixed')),
      discount_value BIGINT NOT NULL CHECK(discount_value > 0),
      min_price BIGINT NOT NULL DEFAULT 7000,
      max_uses INT NOT NULL DEFAULT 10,
      used_count INT NOT NULL DEFAULT 0,
      starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      expires_at TIMESTAMPTZ NOT NULL,
      package_codes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
      tier TEXT NOT NULL DEFAULT 'all' CHECK(tier IN ('all','vip','vvip')),
      active BOOLEAN NOT NULL DEFAULT TRUE,
      created_by BIGINT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    -- Migrate older installations where discount_codes already existed with
    -- a partial/legacy schema. CREATE TABLE IF NOT EXISTS alone does not add
    -- columns to an existing table, which makes the admin INSERT fail.
    ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS min_price BIGINT NOT NULL DEFAULT 7000;
    ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS max_uses INT NOT NULL DEFAULT 10;
    ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS used_count INT NOT NULL DEFAULT 0;
    ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
    ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS package_codes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];
    ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS tier TEXT NOT NULL DEFAULT 'all';
    ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;
    ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS created_by BIGINT;
    ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    -- Legacy rows may not have an expiry. Keep them visible but expired rather
    -- than allowing a NULL expiry to break discount checks.
    UPDATE discount_codes SET expires_at = NOW() WHERE expires_at IS NULL;
    ALTER TABLE discount_codes ALTER COLUMN expires_at SET DEFAULT (NOW() + INTERVAL '24 hours');
    ALTER TABLE discount_codes ALTER COLUMN expires_at SET NOT NULL;

    CREATE TABLE IF NOT EXISTS user_discount_codes(
      user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
      discount_id BIGINT NOT NULL REFERENCES discount_codes(id) ON DELETE CASCADE,
      claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY(user_id,discount_id)
    );
    CREATE TABLE IF NOT EXISTS discount_code_archive(
      code TEXT PRIMARY KEY,
      status TEXT NOT NULL CHECK(status IN ('expired','full','used')),
      archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    ALTER TABLE manual_payments ADD COLUMN IF NOT EXISTS rejection_reason TEXT;
    INSERT INTO discount_codes(code,discount_type,discount_value,min_price,max_uses,expires_at,package_codes,tier)
    VALUES
      ('VIP1HARI20','percent',20,7000,10,NOW()+INTERVAL '365 days',ARRAY['vip_1d'],'vip'),
      ('VIP4HARI20','percent',20,7000,10,NOW()+INTERVAL '365 days',ARRAY['vip_4d'],'vip'),
      ('VIP7HARI20','percent',20,7000,10,NOW()+INTERVAL '365 days',ARRAY['vip_7d'],'vip'),
      ('VIP15HARI20','percent',20,7000,10,NOW()+INTERVAL '365 days',ARRAY['vip_15d'],'vip'),
      ('VVIP1HARI20','percent',20,7000,10,NOW()+INTERVAL '365 days',ARRAY['vvip_1d'],'vvip'),
      ('VVIP4HARI20','percent',20,7000,10,NOW()+INTERVAL '365 days',ARRAY['vvip_4d'],'vvip'),
      ('VVIP7HARI20','percent',20,7000,10,NOW()+INTERVAL '365 days',ARRAY['vvip_7d'],'vvip'),
      ('VVIP15HARI20','percent',20,7000,10,NOW()+INTERVAL '365 days',ARRAY['vvip_15d'],'vvip')
    ON CONFLICT(code) DO NOTHING;
    """)
    await p.fetchval("SELECT 1")

async def execute(q,*a): return await (await get_pool()).execute(q,*a)
async def fetch(q,*a): return await (await get_pool()).fetch(q,*a)
async def fetchrow(q,*a): return await (await get_pool()).fetchrow(q,*a)
async def fetchval(q,*a): return await (await get_pool()).fetchval(q,*a)
