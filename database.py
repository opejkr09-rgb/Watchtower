import os
import uuid
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor


class Database:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL", "")
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable not set")
        self._init()

    def _conn(self):
        return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)

    def _init(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id     BIGINT PRIMARY KEY,
                        username    TEXT NOT NULL,
                        joined_at   TIMESTAMP DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS submissions (
                        id              TEXT PRIMARY KEY,
                        user_id         BIGINT NOT NULL REFERENCES users(user_id),
                        link            TEXT NOT NULL UNIQUE,
                        status          TEXT DEFAULT 'pending',
                        reject_reason   TEXT,
                        submitted_at    TIMESTAMP DEFAULT NOW(),
                        reviewed_at     TIMESTAMP
                    );

                    CREATE INDEX IF NOT EXISTS idx_submissions_user ON submissions(user_id);
                    CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
                """)
            conn.commit()

    def ensure_user(self, user_id: int, username: str):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, username)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
                """, (user_id, username))
            conn.commit()

    def link_already_submitted(self, link: str) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM submissions WHERE link = %s", (link,))
                return cur.fetchone() is not None

    def add_submission(self, user_id: int, link: str) -> str:
        sub_id = str(uuid.uuid4())[:8].upper()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO submissions (id, user_id, link) VALUES (%s, %s, %s)",
                    (sub_id, user_id, link)
                )
            conn.commit()
        return sub_id

    def update_submission_status(
        self,
        sub_id: str,
        status: str,
        reason: Optional[str] = None
    ) -> Optional[dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM submissions WHERE id = %s AND status = 'pending'",
                    (sub_id,)
                )
                row = cur.fetchone()
                if not row:
                    return None

                cur.execute("""
                    UPDATE submissions
                    SET status = %s, reject_reason = %s, reviewed_at = NOW()
                    WHERE id = %s
                """, (status, reason, sub_id))
            conn.commit()
            return {"user_id": row["user_id"], "link": row["link"]}

    def get_user_stats(self, user_id: int) -> dict:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT status, COUNT(*) as count
                    FROM submissions WHERE user_id = %s
                    GROUP BY status
                """, (user_id,))
                rows = cur.fetchall()

        stats = {"approved": 0, "pending": 0, "rejected": 0, "total": 0}
        for row in rows:
            stats[row["status"]] = row["count"]
            stats["total"] += row["count"]
        return stats

    def get_user_rank(self, user_id: int) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT user_id, COUNT(*) as approved_count
                    FROM submissions WHERE status = 'approved'
                    GROUP BY user_id
                    ORDER BY approved_count DESC
                """)
                rows = cur.fetchall()

        for i, row in enumerate(rows):
            if row["user_id"] == user_id:
                return i + 1
        return len(rows) + 1

    def get_leaderboard(self) -> list:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        u.username,
                        u.user_id,
                        COUNT(CASE WHEN s.status = 'approved' THEN 1 END) as approved,
                        COUNT(CASE WHEN s.status = 'pending' THEN 1 END) as pending
                    FROM users u
                    LEFT JOIN submissions s ON u.user_id = s.user_id
                    GROUP BY u.user_id, u.username
                    HAVING COUNT(CASE WHEN s.status = 'approved' THEN 1 END) > 0
                        OR COUNT(CASE WHEN s.status = 'pending' THEN 1 END) > 0
                    ORDER BY approved DESC, pending DESC
                """)
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_pending_submissions(self) -> list:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT s.id, s.link, s.submitted_at, u.username
                    FROM submissions s
                    JOIN users u ON s.user_id = u.user_id
                    WHERE s.status = 'pending'
                    ORDER BY s.submitted_at ASC
                """)
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def reset_all(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM submissions")
            conn.commit()        return [dict(r) for r in rows]

    def reset_all(self):
        with self._conn() as conn:
            conn.execute("DELETE FROM submissions")
