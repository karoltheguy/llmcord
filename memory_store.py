import asyncio
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


class MemoryStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

    def _initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(self.db_path))) as conn, conn:
            conn.execute("CREATE TABLE IF NOT EXISTS user_memory (user_id INTEGER PRIMARY KEY, memory TEXT NOT NULL, updated_at TEXT NOT NULL)")

    async def get(self, user_id: int) -> str | None:
        return await asyncio.to_thread(self._get, user_id)

    def _get(self, user_id: int) -> str | None:
        with closing(sqlite3.connect(str(self.db_path))) as conn, conn:
            cursor = conn.execute("SELECT memory FROM user_memory WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return row[0] if row else None

    async def upsert(self, user_id: int, text: str) -> None:
        await asyncio.to_thread(self._upsert, user_id, text)

    def _upsert(self, user_id: int, text: str) -> None:
        with closing(sqlite3.connect(str(self.db_path))) as conn, conn:
            conn.execute(
                "INSERT INTO user_memory (user_id, memory, updated_at) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET memory = excluded.memory, updated_at = excluded.updated_at",
                (user_id, text, datetime.now(timezone.utc).isoformat()),
            )

    async def delete(self, user_id: int) -> None:
        await asyncio.to_thread(self._delete, user_id)

    def _delete(self, user_id: int) -> None:
        with closing(sqlite3.connect(str(self.db_path))) as conn, conn:
            conn.execute("DELETE FROM user_memory WHERE user_id = ?", (user_id,))
