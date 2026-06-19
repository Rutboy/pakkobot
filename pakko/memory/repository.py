from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite


@dataclass(slots=True)
class MessageRecord:
    role: str
    content: str
    created_at: datetime


@dataclass(slots=True)
class ChatContext:
    chat_id: int
    summary: str | None
    last_activity_at: datetime
    messages: list[MessageRecord]


@dataclass(slots=True)
class ChatStatus:
    chat_id: int
    summary_chars: int
    message_count: int
    last_activity_at: datetime | None


class SQLiteMemoryRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def init(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id INTEGER PRIMARY KEY,
                    summary TEXT,
                    created_at TEXT NOT NULL,
                    last_activity_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_chat_id_id
                    ON messages(chat_id, id);
                """
            )
            await db.commit()

    async def ensure_chat(self, chat_id: int) -> None:
        now = self._now_iso()
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute(
                """
                INSERT INTO chats(chat_id, summary, created_at, last_activity_at)
                VALUES (?, NULL, ?, ?)
                ON CONFLICT(chat_id) DO NOTHING
                """,
                (chat_id, now, now),
            )
            await db.commit()

    async def get_context(self, chat_id: int, recent_limit: int) -> ChatContext:
        await self.ensure_chat(chat_id)
        async with aiosqlite.connect(self._database_path) as db:
            db.row_factory = aiosqlite.Row
            chat = await db.execute_fetchall(
                "SELECT summary, last_activity_at FROM chats WHERE chat_id = ?",
                (chat_id,),
            )
            message_rows = await db.execute_fetchall(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, recent_limit),
            )

        chat_row = chat[0]
        messages = [
            MessageRecord(
                role=str(row["role"]),
                content=str(row["content"]),
                created_at=self._parse_dt(str(row["created_at"])),
            )
            for row in reversed(message_rows)
        ]
        return ChatContext(
            chat_id=chat_id,
            summary=chat_row["summary"],
            last_activity_at=self._parse_dt(str(chat_row["last_activity_at"])),
            messages=messages,
        )

    async def list_messages(self, chat_id: int) -> list[MessageRecord]:
        await self.ensure_chat(chat_id)
        async with aiosqlite.connect(self._database_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE chat_id = ?
                ORDER BY id ASC
                """,
                (chat_id,),
            )
        return [
            MessageRecord(
                role=str(row["role"]),
                content=str(row["content"]),
                created_at=self._parse_dt(str(row["created_at"])),
            )
            for row in rows
        ]

    async def append_message(self, chat_id: int, role: str, content: str) -> None:
        await self.ensure_chat(chat_id)
        now = self._now_iso()
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute(
                "INSERT INTO messages(chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, role, content, now),
            )
            await db.execute(
                "UPDATE chats SET last_activity_at = ? WHERE chat_id = ?",
                (now, chat_id),
            )
            await db.commit()

    async def clear_chat(self, chat_id: int) -> None:
        await self.ensure_chat(chat_id)
        now = self._now_iso()
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            await db.execute(
                "UPDATE chats SET summary = NULL, last_activity_at = ? WHERE chat_id = ?",
                (now, chat_id),
            )
            await db.commit()

    async def replace_summary_and_prune(
        self,
        chat_id: int,
        summary: str,
        keep_recent_messages: int,
    ) -> None:
        await self.ensure_chat(chat_id)
        now = self._now_iso()
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute(
                "UPDATE chats SET summary = ?, last_activity_at = ? WHERE chat_id = ?",
                (summary, now, chat_id),
            )
            await db.execute(
                """
                DELETE FROM messages
                WHERE chat_id = ?
                  AND id NOT IN (
                      SELECT id FROM messages
                      WHERE chat_id = ?
                      ORDER BY id DESC
                      LIMIT ?
                  )
                """,
                (chat_id, chat_id, keep_recent_messages),
            )
            await db.commit()

    async def count_messages(self, chat_id: int) -> int:
        await self.ensure_chat(chat_id)
        async with aiosqlite.connect(self._database_path) as db:
            rows = await db.execute_fetchall(
                "SELECT COUNT(*) AS count FROM messages WHERE chat_id = ?",
                (chat_id,),
            )
        return int(rows[0][0])

    async def status(self, chat_id: int) -> ChatStatus:
        await self.ensure_chat(chat_id)
        async with aiosqlite.connect(self._database_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                """
                SELECT
                    LENGTH(COALESCE(summary, '')) AS summary_chars,
                    last_activity_at,
                    (SELECT COUNT(*) FROM messages WHERE chat_id = ?) AS message_count
                FROM chats
                WHERE chat_id = ?
                """,
                (chat_id, chat_id),
            )
        row = rows[0]
        return ChatStatus(
            chat_id=chat_id,
            summary_chars=int(row["summary_chars"]),
            message_count=int(row["message_count"]),
            last_activity_at=self._parse_dt(str(row["last_activity_at"])),
        )

    @staticmethod
    def _parse_dt(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()
