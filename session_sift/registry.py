from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from time import time

import aiosqlite

from .utils import ensure_parent_dir
from .utils import sha256_text


SCHEMA = """
CREATE TABLE IF NOT EXISTS file_writes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    turn INTEGER NOT NULL,
    msg_index INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    tool_name TEXT,
    session_id TEXT NOT NULL,
    sha256 TEXT
);

CREATE TABLE IF NOT EXISTS error_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    msg_index INTEGER NOT NULL,
    turn INTEGER NOT NULL,
    error_type TEXT,
    session_id TEXT NOT NULL,
    pruned INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS message_tombstones (
    msg_index INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    reason TEXT,
    pruned_at REAL NOT NULL,
    PRIMARY KEY (msg_index, session_id)
);

CREATE TABLE IF NOT EXISTS dna_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    snapshot TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_file_writes_path ON file_writes(file_path, session_id);
CREATE INDEX IF NOT EXISTS idx_error_refs_path ON error_references(file_path, session_id);
CREATE INDEX IF NOT EXISTS idx_tombstones_sess ON message_tombstones(session_id);
"""


class FileRegistry:
    def __init__(self, path: str, session_id: str = "default") -> None:
        self.path = path
        self.session_id = session_id
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            ensure_parent_dir(self.path)
            async with aiosqlite.connect(self.path) as db:
                await db.executescript(SCHEMA)
                await db.execute("PRAGMA journal_mode=WAL;")
                await db.commit()
            self._initialized = True

    async def record_write(
        self,
        file_path: str,
        turn: int,
        msg_index: int,
        tool_name: str,
        sha256: str | None = None,
    ) -> None:
        await self.initialize()
        normalized = self.normalize_path(file_path)
        async with self._write_lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute(
                    """
                    INSERT INTO file_writes(file_path, turn, msg_index, timestamp, tool_name, session_id, sha256)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (normalized, turn, msg_index, time(), tool_name, self.session_id, sha256),
                )
                await db.commit()

    async def has_write_after(self, file_path: str, turn: int) -> bool:
        await self.initialize()
        normalized = self.normalize_path(file_path)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT 1 FROM file_writes
                WHERE file_path = ? AND session_id = ? AND turn >= ?
                LIMIT 1
                """,
                (normalized, self.session_id, turn),
            )
            row = await cursor.fetchone()
            return row is not None

    async def record_error_reference(
        self, file_path: str, msg_index: int, turn: int, error_type: str | None
    ) -> None:
        await self.initialize()
        normalized = self.normalize_path(file_path)
        async with self._write_lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute(
                    """
                    INSERT INTO error_references(file_path, msg_index, turn, error_type, session_id, pruned)
                    VALUES(?, ?, ?, ?, ?, 0)
                    """,
                    (normalized, msg_index, turn, error_type, self.session_id),
                )
                await db.commit()

    async def tombstone(self, msg_index: int, reason: str) -> None:
        await self.initialize()
        async with self._write_lock:
            async with aiosqlite.connect(self.path) as db:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO message_tombstones(msg_index, session_id, reason, pruned_at)
                    VALUES(?, ?, ?, ?)
                    """,
                    (msg_index, self.session_id, reason, time()),
                )
                await db.commit()

    async def export_dna(self, output_path: str | None = None) -> dict:
        await self.initialize()
        now = time()
        payload = {
            "$schema": "https://session-sift.dev/dna/v2.json",
            "session_id": self.session_id,
            "project_root": str(Path.cwd()),
            "created_at": now,
            "last_updated": now,
            "version": 2,
            "files_modified": [],
            "resolved_errors": [],
            "active_todos": [],
            "key_decisions": [],
            "context_summary": "",
            "total_turns": 0,
            "total_tokens_saved": 0,
        }
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT file_path, MAX(turn) FROM file_writes WHERE session_id = ? GROUP BY file_path",
                (self.session_id,),
            )
            for file_path, last_turn in await cursor.fetchall():
                summary, digest = self._summarize_path(file_path)
                payload["files_modified"].append(
                    {
                        "path": file_path,
                        "last_write_turn": last_turn,
                        "sha256": digest,
                        "summary": summary,
                    }
                )
            cursor = await db.execute(
                "SELECT file_path, error_type, turn FROM error_references WHERE session_id = ?",
                (self.session_id,),
            )
            error_rows = await cursor.fetchall()
            for file_path, error_type, turn in error_rows:
                resolved_turn = await self._resolved_turn_for(file_path, turn)
                if resolved_turn is None:
                    continue
                payload["resolved_errors"].append(
                    {
                        "error_type": error_type,
                        "file_path": file_path,
                        "resolved_at_turn": resolved_turn,
                    }
                )

        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    async def import_dna(self, input_path: str) -> dict:
        await self.initialize()
        path = Path(input_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        files_modified = payload.get("files_modified", [])
        async with self._write_lock:
            async with aiosqlite.connect(self.path) as db:
                for entry in files_modified:
                    await db.execute(
                        """
                        INSERT INTO file_writes(file_path, turn, msg_index, timestamp, tool_name, session_id, sha256)
                        VALUES(?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.normalize_path(entry.get("path", "")),
                            entry.get("last_write_turn", 0),
                            -1,
                            time(),
                            "dna_import",
                            self.session_id,
                            entry.get("sha256"),
                        ),
                    )
                await db.execute(
                    "INSERT INTO dna_snapshots(session_id, created_at, snapshot) VALUES(?, ?, ?)",
                    (self.session_id, time(), json.dumps(payload)),
                )
                await db.commit()
        return {
            "session_id": self.session_id,
            "imported_files": len(files_modified),
            "source": str(path),
        }

    async def export_dna_with_context(
        self,
        output_path: str | None = None,
        *,
        total_turns: int = 0,
        total_tokens_saved: int = 0,
        recent_messages: list[dict] | None = None,
    ) -> dict:
        payload = await self.export_dna(output_path=None)
        payload["total_turns"] = total_turns
        payload["total_tokens_saved"] = total_tokens_saved
        payload["active_todos"] = self._collect_active_todos(payload["files_modified"])
        payload["key_decisions"] = self._extract_key_decisions(recent_messages or [])
        payload["context_summary"] = self._build_context_summary(payload)
        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    async def count_entries(self) -> dict:
        await self.initialize()
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM file_writes WHERE session_id = ?",
                (self.session_id,),
            )
            writes = (await cursor.fetchone())[0]
            cursor = await db.execute(
                "SELECT COUNT(*) FROM dna_snapshots WHERE session_id = ?",
                (self.session_id,),
            )
            snapshots = (await cursor.fetchone())[0]
        return {"file_writes": writes, "dna_snapshots": snapshots}

    @staticmethod
    def normalize_path(path: str) -> str:
        raw = path.replace("\\", "/")
        return str(Path(raw)).replace("\\", "/")

    async def _resolved_turn_for(self, file_path: str, turn: int) -> int | None:
        normalized = self.normalize_path(file_path)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT MIN(turn) FROM file_writes
                WHERE file_path = ? AND session_id = ? AND turn >= ?
                """,
                (normalized, self.session_id, turn),
            )
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else None

    def _summarize_path(self, file_path: str) -> tuple[str | None, str | None]:
        path = Path(file_path)
        if not path.is_absolute():
            path = Path.cwd() / file_path
        if not path.exists() or not path.is_file():
            return None, None
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None, None
        digest = sha256_text(content)
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith(("class ", "def ", "async def ")):
                return stripped, digest
        first = next((line.strip() for line in content.splitlines() if line.strip()), None)
        return first, digest

    def _collect_active_todos(self, files_modified: list[dict]) -> list[dict]:
        todos: list[dict] = []
        todo_pattern = re.compile(r"\b(TODO|FIXME)\b[:\s-]*(.*)")
        for file_info in files_modified:
            path = Path(file_info["path"])
            if not path.is_absolute():
                path = Path.cwd() / path
            if not path.exists() or not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, start=1):
                match = todo_pattern.search(line)
                if not match:
                    continue
                todos.append(
                    {
                        "file_path": file_info["path"],
                        "line": line_number,
                        "text": match.group(2).strip() or match.group(1),
                    }
                )
        return todos

    def _extract_key_decisions(self, recent_messages: list[dict]) -> list[dict]:
        decisions: list[dict] = []
        decision_pattern = re.compile(r"\b(chose|decided|prefer|using|use)\b", re.IGNORECASE)
        for message in recent_messages:
            content = str(message.get("content", "")).strip()
            if not decision_pattern.search(content):
                continue
            decisions.append(
                {
                    "turn": message.get("_session_sift", {}).get("turn_index", 0),
                    "summary": content[:240],
                }
            )
        return decisions[:10]

    def _build_context_summary(self, payload: dict) -> str:
        return (
            f"Session captured {payload.get('total_turns', 0)} turns, "
            f"{len(payload.get('files_modified', []))} modified files, "
            f"{len(payload.get('resolved_errors', []))} resolved errors, and "
            f"{payload.get('total_tokens_saved', 0)} tokens saved."
        )
