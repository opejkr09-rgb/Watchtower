import sqlite3
import uuid
from datetime import datetime
from typing import Optional


class Database:
    def __init__(self, db_path: str = "referrals.db"):
        self.db_path = db_path
        self._init()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT NOT NULL,
                    joined_at   TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS submissions (
                    id              TEXT PRIMARY KEY,
                    user_id         INTEGER NOT NULL,
                    link            TEXT NOT NULL,
                    status          TEXT DEFAULT 'pending',
                    reject_reason   TEXT,
                    submitted_at    TEXT DEFAULT (datetime('now')),
                    reviewed_at     TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_submissions_user ON submissions(user_id);
                CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_submissions_link ON submissions(link);
            """)

    def ensure_user(self, user_id: int, username: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
                (user_id, username)
            )
            # Update username in case it changed
            conn.execute(
                "UPDATE users SET username = ? WHERE user_id = ?",
                (username, user_id)
            )

    def link_already_submitted(self, link: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM submissions WHERE link = ?", (link,)
            ).fetchone()
            return row is not None

    def add_submission(self, user_id: int, link: str) -> str:
        sub_id = str(uuid.uuid4())[:8].upper()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO submissions (id, user_id, link) VALUES (?, ?, ?)",
                (sub_id, user_id, link)
            )
        return sub_id

    def update_submission_status(
        self,
        sub_id: str,
        status: str,
        reason: Optional[str] = None
    ) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM submissions WHERE id = ? AND status = 'pending'",
                (sub_id,)
            ).fetchone()

            if not row:
                return None

            conn.execute(
                """UPDATE submissions
                   SET status = ?, reject_reason = ?, reviewed_at = datetime('now')
                   WHERE id = ?""",
                (status, reason, sub_id)
            )

            return {"user_id": row["user_id"], "link": row["link"]}

    def get_user_stats(self, user_id: int) -> dict:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT status, COUNT(*) as count
                   FROM submissions WHERE user_id = ?
                   GROUP BY status""",
                (user_id,)
            ).fetchall()

        stats = {"approved": 0, "pending": 0, "rejected": 0, "total": 0}
        for row in rows:
            stats[row["status"]] = row["count"]
            stats["total"] += row["count"]
        return stats

    def get_user_rank(self, user_id: int) -> int:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT user_id, COUNT(*) as approved_count
                   FROM submissions WHERE status = 'approved'
                   GROUP BY user_id
                   ORDER BY approved_count DESC"""
            ).fetchall()

        for i, row in enumerate(rows):
            if row["user_id"] == user_id:
                return i + 1
        return len(rows) + 1  # Not on board yet

    def get_leaderboard(self) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT
                       u.username,
                       u.user_id,
                       COUNT(CASE WHEN s.status = 'approved' THEN 1 END) as approved,
                       COUNT(CASE WHEN s.status = 'pending' THEN 1 END) as pending
                   FROM users u
                   LEFT JOIN submissions s ON u.user_id = s.user_id
                   GROUP BY u.user_id
                   HAVING approved > 0 OR pending > 0
                   ORDER BY approved DESC, pending DESC"""
            ).fetchall()
        return [dict(r) for r in rows]

    def get_pending_submissions(self) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT s.id, s.link, s.submitted_at, u.username
                   FROM submissions s
                   JOIN users u ON s.user_id = u.user_id
                   WHERE s.status = 'pending'
                   ORDER BY s.submitted_at ASC"""
            ).fetchall()
        return [dict(r) for r in rows]

    def reset_all(self):
        with self._conn() as conn:
            conn.execute("DELETE FROM submissions")
