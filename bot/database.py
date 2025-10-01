"""SQLite persistence for the UIABot."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - only for type checkers
    from .config import Employee


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
                    employee_code TEXT,
                    telegram_user_id INTEGER NOT NULL,
                    user_full_name TEXT NOT NULL,
                    department TEXT NOT NULL,
                    issue_type TEXT NOT NULL,
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
                CREATE TABLE IF NOT EXISTS employees (
                    code TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    department TEXT NOT NULL,
                    position TEXT NOT NULL,
                    phone TEXT NOT NULL
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
            self._ensure_call_columns(conn)
            conn.commit()

    def _ensure_call_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(calls)")}
        if "employee_code" not in columns:
            conn.execute("ALTER TABLE calls ADD COLUMN employee_code TEXT")

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
        employee_code: str,
        telegram_user_id: int,
        full_name: str,
        department: str,
        issue_type: str,
        basic_guidance: str,
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO calls (
                    employee_code,
                    telegram_user_id,
                    user_full_name,
                    department,
                    issue_type,
                    basic_guidance,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    employee_code,
                    telegram_user_id,
                    full_name,
                    department,
                    issue_type,
                    basic_guidance,
                    "basic_guidance_provided",
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def sync_employees(self, employees: Iterable["Employee"]) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM employees")
            if employees:
                conn.executemany(
                    """
                    INSERT INTO employees (code, full_name, department, position, phone)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            employee.code,
                            employee.full_name,
                            employee.department,
                            employee.position,
                            employee.phone,
                        )
                        for employee in employees
                    ],
                )
            conn.commit()

    def get_employee_by_code(self, code: str) -> Optional[Dict[str, str]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT code, full_name, department, position, phone
                FROM employees
                WHERE code = ?
                """,
                (code,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            keys = ["code", "full_name", "department", "position", "phone"]
            return dict(zip(keys, row))

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

    def get_call(self, call_id: int) -> Optional[Dict[str, object]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id,
                       employee_code,
                       telegram_user_id,
                       user_full_name,
                       department,
                       issue_type,
                       basic_guidance,
                       issue_description,
                       ai_guidance,
                       status,
                       assigned_engineer
                FROM calls
                WHERE id = ?
                """,
                (call_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            keys = [
                "id",
                "employee_code",
                "telegram_user_id",
                "user_full_name",
                "department",
                "issue_type",
                "basic_guidance",
                "issue_description",
                "ai_guidance",
                "status",
                "assigned_engineer",
            ]
            return dict(zip(keys, row))

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
            by_engineer = conn.execute(
                """
                SELECT assigned_engineer,
                       COUNT(*) AS total_calls,
                       SUM(CASE WHEN status LIKE 'resolved%' THEN 1 ELSE 0 END) AS resolved_calls
                FROM calls
                WHERE assigned_engineer IS NOT NULL
                GROUP BY assigned_engineer
                """
            ).fetchall()

        return {
            "total": int(total_calls),
            "by_department": [(row[0], int(row[1])) for row in by_department],
            "by_issue": [(row[0], int(row[1])) for row in by_issue],
            "statuses": [(row[0], int(row[1])) for row in statuses],
            "by_engineer": [
                (row[0], int(row[1]), int(row[2] or 0)) for row in by_engineer
            ],
        }

