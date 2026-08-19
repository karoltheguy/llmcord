import asyncio
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


@dataclass
class Claim:
    id: int | None
    source_id: int
    subjects: set[int]
    text: str
    created_at: str | None = None


def _placeholders(values) -> str:
    return ",".join("?" for _ in values)


def _subjects_intersect_sql(subject_ids) -> str:
    return (
        "EXISTS (SELECT 1 FROM claim_subjects WHERE claim_subjects.claim_id = claims.id "
        f"AND claim_subjects.subject_id IN ({_placeholders(subject_ids)}))"
    )


class MemoryStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

    def _initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            with conn:
                conn.execute("CREATE TABLE IF NOT EXISTS user_memory (user_id INTEGER PRIMARY KEY, memory TEXT NOT NULL, updated_at TEXT NOT NULL)")
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS claims ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "source_id INTEGER NOT NULL, "
                    "text TEXT NOT NULL, "
                    "created_at TEXT NOT NULL, "
                    "updated_at TEXT NOT NULL)"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS claim_subjects ("
                    "claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE, "
                    "subject_id INTEGER NOT NULL, "
                    "PRIMARY KEY (claim_id, subject_id))"
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_claim_subjects_subject_id ON claim_subjects(subject_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_source_id ON claims(source_id)")

    async def get(self, user_id: int) -> str | None:
        return await asyncio.to_thread(self._get, user_id)

    def _get(self, user_id: int) -> str | None:
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            with conn:
                cursor = conn.execute("SELECT memory FROM user_memory WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                return row[0] if row else None

    async def upsert(self, user_id: int, text: str) -> None:
        await asyncio.to_thread(self._upsert, user_id, text)

    def _upsert(self, user_id: int, text: str) -> None:
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO user_memory (user_id, memory, updated_at) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET memory = excluded.memory, updated_at = excluded.updated_at",
                    (user_id, text, datetime.now(timezone.utc).isoformat()),
                )

    async def delete(self, user_id: int) -> None:
        await asyncio.to_thread(self._delete, user_id)

    def _delete(self, user_id: int) -> None:
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            with conn:
                conn.execute("DELETE FROM user_memory WHERE user_id = ?", (user_id,))

    async def replace_claims(self, source_id: int, scope_subject_ids: set[int], claims: list[Claim]) -> None:
        await asyncio.to_thread(self._replace_claims, source_id, scope_subject_ids, claims)

    def _replace_claims(self, source_id: int, scope_subject_ids: set[int], claims: list[Claim]) -> None:
        with closing(self._connect()) as conn:
            with conn:
                in_scope_ids: set[int] = set()
                if scope_subject_ids:
                    cursor = conn.execute(
                        f"SELECT id FROM claims WHERE source_id = ? AND {_subjects_intersect_sql(scope_subject_ids)}",
                        (source_id, *scope_subject_ids),
                    )
                    in_scope_ids = {row[0] for row in cursor.fetchall()}

                echoed_claims = [claim for claim in claims if claim.id is not None and claim.id in in_scope_ids]
                new_claims = [claim for claim in claims if not (claim.id is not None and claim.id in in_scope_ids)]
                echoed_ids = {claim.id for claim in echoed_claims}

                ids_to_delete = in_scope_ids - echoed_ids
                if ids_to_delete:
                    conn.execute(
                        f"DELETE FROM claims WHERE id IN ({_placeholders(ids_to_delete)})",
                        tuple(ids_to_delete),
                    )

                now = datetime.now(timezone.utc).isoformat()

                for claim in echoed_claims:
                    conn.execute(
                        "UPDATE claims SET text = ?, updated_at = ? WHERE id = ? AND source_id = ?",
                        (claim.text, now, claim.id, source_id),
                    )
                    conn.execute(
                        "DELETE FROM claim_subjects WHERE claim_id = ?",
                        (claim.id,),
                    )
                    conn.executemany(
                        "INSERT INTO claim_subjects (claim_id, subject_id) VALUES (?, ?)",
                        [(claim.id, subject_id) for subject_id in claim.subjects],
                    )

                for claim in new_claims:
                    cursor = conn.execute(
                        "INSERT INTO claims (source_id, text, created_at, updated_at) VALUES (?, ?, ?, ?)",
                        (claim.source_id, claim.text, now, now),
                    )
                    claim_id = cursor.lastrowid
                    conn.executemany(
                        "INSERT INTO claim_subjects (claim_id, subject_id) VALUES (?, ?)",
                        [(claim_id, subject_id) for subject_id in claim.subjects],
                    )

    async def claims_by(self, source_id: int, subject_ids: set[int] | None = None, limit: int = 50) -> list[Claim]:
        return await asyncio.to_thread(self._claims_by, source_id, subject_ids, limit)

    def _claims_by(self, source_id: int, subject_ids: set[int] | None, limit: int) -> list[Claim]:
        with closing(self._connect()) as conn:
            with conn:
                if subject_ids:
                    cursor = conn.execute(
                        f"SELECT id, source_id, text, created_at FROM claims WHERE source_id = ? "
                        f"AND {_subjects_intersect_sql(subject_ids)} "
                        f"ORDER BY created_at DESC, id DESC LIMIT ?",
                        (source_id, *subject_ids, limit),
                    )
                else:
                    cursor = conn.execute(
                        "SELECT id, source_id, text, created_at FROM claims WHERE source_id = ? "
                        "ORDER BY created_at DESC, id DESC LIMIT ?",
                        (source_id, limit),
                    )
                return self._hydrate_claims(conn, cursor.fetchall())

    async def claims_about(self, subject_ids: set[int], exclude_source: int | None = None, limit: int = 50) -> list[Claim]:
        return await asyncio.to_thread(self._claims_about, subject_ids, exclude_source, limit)

    def _claims_about(self, subject_ids: set[int], exclude_source: int | None, limit: int) -> list[Claim]:
        with closing(self._connect()) as conn:
            with conn:
                params: list[object] = list(subject_ids)
                query = f"SELECT id, source_id, text, created_at FROM claims WHERE {_subjects_intersect_sql(subject_ids)}"
                if exclude_source is not None:
                    query += " AND source_id != ?"
                    params.append(exclude_source)
                query += " ORDER BY created_at DESC, id DESC LIMIT ?"
                params.append(limit)
                cursor = conn.execute(query, params)
                return self._hydrate_claims(conn, cursor.fetchall())

    async def delete_claims_for(self, user_id: int) -> None:
        await asyncio.to_thread(self._delete_claims_for, user_id)

    def _delete_claims_for(self, user_id: int) -> None:
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    "DELETE FROM claims WHERE source_id = ? "
                    "OR id IN (SELECT claim_id FROM claim_subjects WHERE subject_id = ?)",
                    (user_id, user_id),
                )

    def _hydrate_claims(self, conn: sqlite3.Connection, rows: list[tuple]) -> list[Claim]:
        if not rows:
            return []
        claim_ids = [row[0] for row in rows]
        subject_rows = conn.execute(
            f"SELECT claim_id, subject_id FROM claim_subjects WHERE claim_id IN ({_placeholders(claim_ids)})",
            claim_ids,
        ).fetchall()
        subjects_by_claim: dict[int, set[int]] = {claim_id: set() for claim_id in claim_ids}
        for claim_id, subject_id in subject_rows:
            subjects_by_claim[claim_id].add(subject_id)
        return [
            Claim(
                id=row[0],
                source_id=row[1],
                subjects=subjects_by_claim[row[0]],
                text=row[2],
                created_at=row[3],
            )
            for row in rows
        ]
