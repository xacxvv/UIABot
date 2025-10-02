"""SQLite persistence for the UIABot."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Iterable


class Database:
    """Thin wrapper around SQLite to store calls and assignments."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._initialise()

    def _initialise(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER NOT NULL,
                    user_full_name TEXT NOT NULL,
                    department TEXT NOT NULL,
                    issue_type TEXT NOT NULL,
                    employee_code TEXT,
                    basic_guidance TEXT,
                    issue_description TEXT,
                    ai_guidance TEXT,
                    status TEXT NOT NULL,
                    assigned_engineer TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS trg_calls_updated
                AFTER UPDATE ON calls
                BEGIN
                    UPDATE calls SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END;
                """
            )
            conn.commit()

            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(calls)").fetchall()
            }
            if "employee_code" not in columns:
                conn.execute(
                    "ALTER TABLE calls ADD COLUMN employee_code TEXT"
                )
                conn.commit()

    @contextmanager
    def _get_connection(self) -> Iterable[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(self._path)
            try:
                yield conn
            finally:
                conn.close()

    # CRUD helpers ---------------------------------------------------------
    def create_call(
        self,
        telegram_user_id: int,
        full_name: str,
        department: str,
        issue_type: str,
        employee_code: str | None,
        basic_guidance: str,
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO calls (
                    telegram_user_id,
                    user_full_name,
                    department,
                    issue_type,
                    employee_code,
                    basic_guidance,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_user_id,
                    full_name,
                    department,
                    issue_type,
                    employee_code,
                    basic_guidance,
                    "basic_guidance_provided",
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def update_issue_description(self, call_id: int, description: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE calls SET issue_description = ? WHERE id = ?",
                (description, call_id),
            )
            conn.commit()

    def update_ai_guidance(self, call_id: int, guidance: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE calls SET ai_guidance = ?, status = ? WHERE id = ?",
                (guidance, "ai_guidance_provided", call_id),
            )
            conn.commit()

    def mark_status(self, call_id: int, status: str) -> None:
        with self._get_connection() as conn:
            conn.execute("UPDATE calls SET status = ? WHERE id = ?", (status, call_id))
            conn.commit()

    def assign_engineer(self, call_id: int, engineer_name: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE calls SET assigned_engineer = ?, status = ? WHERE id = ?",
                (engineer_name, "escalated_to_engineer", call_id),
            )
            conn.commit()

    # Reporting ------------------------------------------------------------
    def _count_for_today(self, engineer_name: str) -> int:
        today = datetime.now(timezone.utc).date()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*)
                FROM calls
                WHERE assigned_engineer = ?
                  AND DATE(created_at) = ?
                """,
                (engineer_name, today.isoformat()),
            )
            result = cursor.fetchone()
            return int(result[0] if result else 0)

    def engineer_loads(self, engineer_names: Iterable[str]) -> Dict[str, int]:
        return {name: self._count_for_today(name) for name in engineer_names}

    def summary(self) -> Dict[str, object]:
        with self._get_connection() as conn:
            total_calls = conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
            by_department = conn.execute(
                "SELECT department, COUNT(*) FROM calls GROUP BY department"
            ).fetchall()
            by_issue = conn.execute(
                "SELECT issue_type, COUNT(*) FROM calls GROUP BY issue_type"
            ).fetchall()
            statuses = conn.execute(
                "SELECT status, COUNT(*) FROM calls GROUP BY status"
            ).fetchall()

        return {
            "total": int(total_calls),
            "by_department": [(row[0], int(row[1])) for row in by_department],
            "by_issue": [(row[0], int(row[1])) for row in by_issue],
            "statuses": [(row[0], int(row[1])) for row in statuses],
        }

