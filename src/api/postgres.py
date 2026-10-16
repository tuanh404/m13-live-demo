"""Optional persistent review store for hosts without persistent local disks.

Only the store's internal, parameterized SQL is accepted. Values never become SQL.
Transactions taking SQLite's writer lock take a PostgreSQL advisory transaction
lock instead, preserving lost-ACK deduplication and login/start atomicity.
"""

from contextlib import contextmanager

CONNECTION_OPTIONS = {
    "connect_timeout": 15,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
    "tcp_user_timeout": 30000,
    "options": "-c statement_timeout=20000 -c lock_timeout=15000",
    "application_name": "m13-review",
}


class Record(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


def record_factory(cursor):
    columns = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: Record(zip(columns, values, strict=True))


class Database:
    def __init__(self, db):
        self.db = db

    def execute(self, query, params=()):
        if query == "BEGIN IMMEDIATE":
            return self.db.execute("SELECT pg_advisory_xact_lock(731905)")
        # Queries are fixed internal statements; no client SQL or identifiers.
        return self.db.execute(query.replace("?", "%s"), params)


def initialize(db):
    db.execute("SELECT pg_advisory_xact_lock(731905)")
    db.execute("""CREATE TABLE IF NOT EXISTS verdicts (
        id BIGSERIAL PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
        payload_hash TEXT NOT NULL, image_id TEXT NOT NULL, verdict TEXT NOT NULL,
        reviewer TEXT NOT NULL, seconds_spent DOUBLE PRECISION NOT NULL,
        note TEXT, obj_ids TEXT NOT NULL, created_at TEXT NOT NULL,
        batch_id TEXT, queue_id TEXT NOT NULL, model_version TEXT NOT NULL,
        rank INTEGER NOT NULL, is_audit INTEGER NOT NULL, session_id TEXT NOT NULL,
        review_order TEXT NOT NULL,
        audit_policy_id TEXT NOT NULL DEFAULT 'legacy-every10',
        audit_policy_version TEXT NOT NULL DEFAULT 'legacy-every10',
        audit_source_queue_id TEXT, source_rank INTEGER
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS verdict_queue ON verdicts(queue_id,reviewer,session_id)")
    db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute("""CREATE OR REPLACE FUNCTION m13_verdict_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'verdict history is append-only'; END $$""")
    # Existing readers (including a backup) must not block application restarts.
    # DROP TRIGGER would need an exclusive table lock even when nothing changed.
    db.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='verdicts_append_only'
            AND tgrelid='verdicts'::regclass AND NOT tgisinternal) THEN
            CREATE TRIGGER verdicts_append_only BEFORE UPDATE OR DELETE ON verdicts
                FOR EACH ROW EXECUTE FUNCTION m13_verdict_append_only();
        END IF;
    END $$""")


@contextmanager
def connection(store):
    import psycopg

    # Never interpolate the URL into an exception or log message.
    try:
        db = psycopg.connect(store.database_url, **CONNECTION_OPTIONS, row_factory=record_factory)
    except psycopg.Error:
        raise RuntimeError("Không kết nối được database; kiểm tra cấu hình backend") from None
    with db:
        with store._schema_lock:
            if not store._initialized:
                initialize(db)
                db.commit()
                store._initialized = True
        db.execute("SET LOCAL statement_timeout = '20s'")
        db.execute("SET LOCAL lock_timeout = '15s'")
        yield Database(db)
