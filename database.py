import os
import uuid
import asyncio
import asyncpg
from typing import Optional


class Database:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL", "")
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable not set")
        self._pool = None

    async def init(self):
        self._pool = await asyncpg.create_pool(self.db_url)
        async with self._pool.acquire() as conn:
            await conn.execute("""
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

    async def ensure_user(self, user_id: int, username: str):
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, username)
                VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
            """, user_id, username)

    async def link_already_submitted(self, link: str) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM submissions WHERE link = $1", link)
            return row is not None

    async def add_submission(self, user_id: int, link: str) -> str:
        sub_id = str(uuid.uuid4())[:8].upper()
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO submissions (id, user_id, link) VALUES ($1, $2, $3)",
                sub_id, user_id, link
            )
        return sub_id

    async def update_submission_status(
        self,
        sub_id: str,
        status: str,
        reason: Optional[str] = None
    ) -> Optional[dict]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM submissions WHERE id = $1 AND status = 'pending'",
                sub_id
            )
            if not row:
                return None
            await conn.execute("""
                UPDATE submissions
                SET status = $1, reject_reason = $2, reviewed_at = NOW()
                WHERE id = $3
            """, status, reason, sub_id)
            return {"user_id": row["user_id"], "link": row["link"]}

    async def get_user_stats(self, user_id: int) -> dict:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT status, COUNT(*) as count
                FROM submissions WHERE user_id = $1
                GROUP BY status
            """, user_id)
        stats = {"approved": 0, "pending": 0, "rejected": 0, "total": 0}
        for row in rows:
            stats[row["status"]] = row["count"]
            stats["total"] += row["count"]
        return stats

    async def get_user_rank(self, user_id: int) -> int:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, COUNT(*) as approved_count
                FROM submissions WHERE status = 'approved'
                GROUP BY user_id
                ORDER BY approved_count DESC
            """)
        for i, row in enumerate(rows):
            if row["user_id"] == user_id:
                return i + 1
        return len(rows) + 1

    async def get_leaderboard(self) -> list:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
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
        return [dict(r) for r in rows]

    async def get_pending_submissions(self) -> list:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.id, s.link, s.submitted_at, u.username
                FROM submissions s
                JOIN users u ON s.user_id = u.user_id
                WHERE s.status = 'pending'
                ORDER BY s.submitted_at ASC
            """)
        return [dict(r) for r in rows]

    async def reset_all(self):
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM submissions")
