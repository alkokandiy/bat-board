"""
Idempotent fix for production: completes what migration 008 failed to do.
Safe to run multiple times — every statement is guarded.

Production state before this script:
  - bat_alfred_sessions exists (empty, 0 rows)
  - bat_alfred_messages has NO session_id column
  - bat_account has NO active_alfred_session_id column
  - alembic_version = 007
"""
import sys
import psycopg2

DATABASE_URL = sys.argv[1] if len(sys.argv) > 1 else None
if not DATABASE_URL:
    print("Usage: python scripts/fix_008_production.py <DATABASE_URL>")
    sys.exit(1)

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = False
cur = conn.cursor()

try:
    # 1. Add session_id to bat_alfred_messages if missing
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'bat_alfred_messages' AND column_name = 'session_id'
            ) THEN
                ALTER TABLE bat_alfred_messages ADD COLUMN session_id INTEGER;
                CREATE INDEX ix_bat_alfred_messages_session_id ON bat_alfred_messages (session_id);
                ALTER TABLE bat_alfred_messages
                    ADD CONSTRAINT fk_bat_alfred_messages_session_id
                    FOREIGN KEY (session_id) REFERENCES bat_alfred_sessions(id) ON DELETE CASCADE;
                RAISE NOTICE 'Added session_id to bat_alfred_messages';
            ELSE
                RAISE NOTICE 'session_id already exists on bat_alfred_messages';
            END IF;
        END $$;
    """)
    conn.commit()
    print("[OK] session_id column on bat_alfred_messages")

    # 2. Backfill: for each owner with unassigned messages, create one session
    #    and point all their messages at it. Uses NOW() (Postgres-correct).
    cur.execute("""
        DO $$
        DECLARE
            r RECORD;
            new_id INTEGER;
        BEGIN
            FOR r IN
                SELECT DISTINCT owner_id
                FROM bat_alfred_messages
                WHERE session_id IS NULL
            LOOP
                INSERT INTO bat_alfred_sessions (title, created_at, updated_at, owner_id)
                VALUES ('Earlier conversation', NOW(), NOW(), r.owner_id)
                RETURNING id INTO new_id;

                UPDATE bat_alfred_messages
                SET session_id = new_id
                WHERE owner_id = r.owner_id AND session_id IS NULL;

                RAISE NOTICE 'Backfilled owner_id=%: session_id=%', r.owner_id, new_id;
            END LOOP;
        END $$;
    """)
    conn.commit()
    print("[OK] Backfill complete")

    # 3. Make session_id NOT NULL (only if no NULLs remain)
    cur.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM bat_alfred_messages WHERE session_id IS NULL LIMIT 1
            ) THEN
                RAISE WARNING 'Still have NULL session_ids — skipping NOT NULL constraint';
            ELSE
                ALTER TABLE bat_alfred_messages ALTER COLUMN session_id SET NOT NULL;
                RAISE NOTICE 'session_id is now NOT NULL';
            END IF;
        END $$;
    """)
    conn.commit()
    print("[OK] session_id NOT NULL constraint")

    # 4. Add active_alfred_session_id to bat_account if missing
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'bat_account' AND column_name = 'active_alfred_session_id'
            ) THEN
                ALTER TABLE bat_account ADD COLUMN active_alfred_session_id INTEGER;
                ALTER TABLE bat_account
                    ADD CONSTRAINT fk_bat_account_active_alfred_session_id
                    FOREIGN KEY (active_alfred_session_id) REFERENCES bat_alfred_sessions(id) ON DELETE SET NULL;
                RAISE NOTICE 'Added active_alfred_session_id to bat_account';
            ELSE
                RAISE NOTICE 'active_alfred_session_id already exists on bat_account';
            END IF;
        END $$;
    """)
    conn.commit()
    print("[OK] active_alfred_session_id column on bat_account")

    # 5. Update alembic_version to 008
    cur.execute("""
        DO $$
        BEGIN
            UPDATE alembic_version SET version_num = '008';
            IF NOT FOUND THEN
                INSERT INTO alembic_version (version_num) VALUES ('008');
            END IF;
            RAISE NOTICE 'alembic_version set to 008';
        END $$;
    """)
    conn.commit()
    print("[OK] alembic_version = 008")

    print("\nAll done. Production schema is now complete.")

except Exception as e:
    conn.rollback()
    print(f"ERROR: {e}")
    conn.close()
    sys.exit(1)

conn.close()
