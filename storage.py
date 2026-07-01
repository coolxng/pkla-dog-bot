"""SQLite persistence for universal memory and conversation history."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class StateStore:
    def __init__(self, db_path: Path, *, enabled: bool) -> None:
        self.enabled = enabled
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        if not enabled:
            return
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        assert self._conn is not None
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS universal_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_type TEXT NOT NULL CHECK (scope_type IN ('dm', 'channel')),
                scope_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (scope_type, scope_id, position)
            );

            CREATE INDEX IF NOT EXISTS idx_conversation_scope
                ON conversation_messages(scope_type, scope_id, position);
            """
        )
        self._conn.commit()

    def load_universal_memory(self) -> list[str]:
        if not self.enabled or self._conn is None:
            return []
        rows = self._conn.execute(
            "SELECT fact FROM universal_memory ORDER BY id ASC"
        ).fetchall()
        return [row[0] for row in rows]

    def save_universal_memory(self, facts: list[str]) -> None:
        if not self.enabled or self._conn is None:
            return
        now = datetime.now(UTC).isoformat()
        self._conn.execute("DELETE FROM universal_memory")
        for fact in facts:
            self._conn.execute(
                "INSERT OR REPLACE INTO universal_memory (fact, created_at) VALUES (?, ?)",
                (fact, now),
            )
        self._conn.commit()

    def clear_universal_memory(self) -> None:
        if not self.enabled or self._conn is None:
            return
        self._conn.execute("DELETE FROM universal_memory")
        self._conn.commit()

    def load_dm_histories(self) -> dict[int, list[dict[str, str]]]:
        return self._load_histories("dm")

    def load_channel_histories(self) -> dict[int, list[dict[str, str]]]:
        return self._load_histories("channel")

    def _load_histories(self, scope_type: str) -> dict[int, list[dict[str, str]]]:
        if not self.enabled or self._conn is None:
            return {}
        rows = self._conn.execute(
            """
            SELECT scope_id, role, content
            FROM conversation_messages
            WHERE scope_type = ?
            ORDER BY scope_id ASC, position ASC
            """,
            (scope_type,),
        ).fetchall()
        histories: dict[int, list[dict[str, str]]] = {}
        for scope_id, role, content in rows:
            histories.setdefault(scope_id, []).append(
                {"role": role, "content": content}
            )
        return histories

    def save_dm_history(self, user_id: int, messages: list[dict[str, str]]) -> None:
        self._save_history("dm", user_id, messages)

    def save_channel_history(
        self, channel_id: int, messages: list[dict[str, str]]
    ) -> None:
        self._save_history("channel", channel_id, messages)

    def _save_history(
        self,
        scope_type: str,
        scope_id: int,
        messages: list[dict[str, str]],
    ) -> None:
        if not self.enabled or self._conn is None:
            return
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "DELETE FROM conversation_messages WHERE scope_type = ? AND scope_id = ?",
            (scope_type, scope_id),
        )
        for position, message in enumerate(messages):
            self._conn.execute(
                """
                INSERT INTO conversation_messages
                    (scope_type, scope_id, position, role, content, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    scope_type,
                    scope_id,
                    position,
                    message["role"],
                    message["content"],
                    now,
                ),
            )
        self._conn.commit()

    def delete_dm_history(self, user_id: int) -> None:
        self._delete_history("dm", user_id)

    def delete_channel_history(self, channel_id: int) -> None:
        self._delete_history("channel", channel_id)

    def _delete_history(self, scope_type: str, scope_id: int) -> None:
        if not self.enabled or self._conn is None:
            return
        self._conn.execute(
            "DELETE FROM conversation_messages WHERE scope_type = ? AND scope_id = ?",
            (scope_type, scope_id),
        )
        self._conn.commit()

    def delete_dm_histories_except(self, keep_user_ids: set[int]) -> None:
        self._delete_histories_except("dm", keep_user_ids)

    def delete_channel_histories_except(self, keep_channel_ids: set[int]) -> None:
        self._delete_histories_except("channel", keep_channel_ids)

    def _delete_histories_except(self, scope_type: str, keep_ids: set[int]) -> None:
        if not self.enabled or self._conn is None:
            return
        if not keep_ids:
            self._conn.execute(
                "DELETE FROM conversation_messages WHERE scope_type = ?",
                (scope_type,),
            )
        else:
            placeholders = ",".join("?" for _ in keep_ids)
            self._conn.execute(
                f"""
                DELETE FROM conversation_messages
                WHERE scope_type = ? AND scope_id NOT IN ({placeholders})
                """,
                (scope_type, *keep_ids),
            )
        self._conn.commit()


def default_state_store() -> StateStore:
    enabled = os.environ.get("PERSIST_STATE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    db_path = Path(
        os.environ.get("STATE_DB_PATH", "bot_state.db").strip() or "bot_state.db"
    )
    return StateStore(db_path, enabled=enabled)