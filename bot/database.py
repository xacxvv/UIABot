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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS employee_codes (
                    code TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    department TEXT
                )
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

            employee_columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(employee_codes)").fetchall()
            }
            if "department" not in employee_columns:
                conn.execute(
                    "ALTER TABLE employee_codes ADD COLUMN department TEXT"
                )
                conn.commit()

    def has_employee_codes(self) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM employee_codes LIMIT 1"
            )
            return cursor.fetchone() is not None

    def is_employee_code_allowed(self, code: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM employee_codes WHERE code = ?",
                (code,),
            )
            return cursor.fetchone() is not None

    def add_employee(self, code: str, full_name: str, department: str | None) -> bool:
        """Add or update an employee record.

        Returns ``True`` when a new record was created and ``False`` when an
        existing record was updated.
        """

        department = department.strip() if department else None

        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT 1 FROM employee_codes WHERE code = ?",
                (code,),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO employee_codes (code, full_name, department)
                VALUES (?, ?, ?)
                ON CONFLICT(code) DO UPDATE
                    SET full_name = excluded.full_name,
                        department = COALESCE(excluded.department, employee_codes.department)
                """,
                (code, full_name, department),
            )
            conn.commit()
            return existing is None

    def get_employee(self, code: str) -> Dict[str, str] | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT code, full_name, department FROM employee_codes WHERE code = ?",
                (code,),
            ).fetchone()

        if row is None:
            return None

        return {
            "code": row["code"],
            "full_name": row["full_name"],
            "department": row["department"],
        }

    @contextmanager
    def _get_connection(self) -> Iterable[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(self._path)
            conn.row_factory = sqlite3.Row
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

    def assign_engineer_if_unassigned(self, call_id: int, engineer_name: str) -> bool:
        """Assign an engineer only when the call is still unassigned."""

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE calls
                   SET assigned_engineer = ?,
                       status = ?
                 WHERE id = ?
                   AND (assigned_engineer IS NULL OR assigned_engineer = '')
                """,
                (engineer_name, "escalated_to_engineer", call_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def is_call_assigned(self, call_id: int) -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT assigned_engineer FROM calls WHERE id = ?",
                (call_id,),
            ).fetchone()
            return bool(row and row[0])

    def get_call_details(self, call_id: int) -> Dict[str, object] | None:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT id,
                       user_full_name,
                       department,
                       issue_type,
                       employee_code,
                       issue_description,
                       ai_guidance,
                       status,
                       assigned_engineer
                  FROM calls
                 WHERE id = ?
                """,
                (call_id,),
            ).fetchone()

        if row is None:
            return None

        return {
            "id": int(row["id"]),
            "user_full_name": row["user_full_name"],
            "department": row["department"],
            "issue_type": row["issue_type"],
            "employee_code": row["employee_code"],
            "issue_description": row["issue_description"],
            "ai_guidance": row["ai_guidance"],
            "status": row["status"],
            "assigned_engineer": row["assigned_engineer"],
        }

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

    def summary_between(self, start_date: datetime, end_date: datetime) -> Dict[str, object]:
        """Return summary statistics between inclusive date boundaries."""

        start = start_date.date().isoformat()
        end = end_date.date().isoformat()

        with self._get_connection() as conn:
            total_calls = conn.execute(
                "SELECT COUNT(*) FROM calls WHERE DATE(created_at) BETWEEN ? AND ?",
                (start, end),
            ).fetchone()[0]
            by_department = conn.execute(
                """
                SELECT department, COUNT(*)
                  FROM calls
                 WHERE DATE(created_at) BETWEEN ? AND ?
                 GROUP BY department
                """,
                (start, end),
            ).fetchall()
            by_issue = conn.execute(
                """
                SELECT issue_type, COUNT(*)
                  FROM calls
                 WHERE DATE(created_at) BETWEEN ? AND ?
                 GROUP BY issue_type
                """,
                (start, end),
            ).fetchall()
            statuses = conn.execute(
                """
                SELECT status, COUNT(*)
                  FROM calls
                 WHERE DATE(created_at) BETWEEN ? AND ?
                 GROUP BY status
                """,
                (start, end),
            ).fetchall()

        return {
            "total": int(total_calls),
            "by_department": [(row[0], int(row[1])) for row in by_department],
            "by_issue": [(row[0], int(row[1])) for row in by_issue],
            "statuses": [(row[0], int(row[1])) for row in statuses],
        }

