from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from typing import Dict, Iterator, List, Optional, Tuple

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS students (
    student_id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    pin VARCHAR(10) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS items (
    item_id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    condition VARCHAR(50) NOT NULL,
    rental_price_per_day REAL NOT NULL CHECK(rental_price_per_day > 0),
    lender_id VARCHAR(10) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE' CHECK(status IN ('AVAILABLE', 'REQUESTED', 'BORROWED')),
    FOREIGN KEY (lender_id) REFERENCES students(student_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS borrow_requests (
    request_id VARCHAR(10) PRIMARY KEY,
    item_id VARCHAR(10) NOT NULL,
    borrower_id VARCHAR(10) NOT NULL,
    lender_id VARCHAR(10) NOT NULL,
    duration_days INTEGER NOT NULL CHECK(duration_days > 0),
    requested_on DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'CANCELLED')),
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE RESTRICT,
    FOREIGN KEY (borrower_id) REFERENCES students(student_id) ON DELETE RESTRICT,
    FOREIGN KEY (lender_id) REFERENCES students(student_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id VARCHAR(10) PRIMARY KEY,
    request_id VARCHAR(10) NOT NULL,
    item_id VARCHAR(10) NOT NULL,
    borrower_id VARCHAR(10) NOT NULL,
    lender_id VARCHAR(10) NOT NULL,
    start_date DATE NOT NULL,
    due_date DATE NOT NULL,
    duration_days INTEGER NOT NULL CHECK(duration_days > 0),
    daily_rent REAL NOT NULL CHECK(daily_rent > 0),
    rental_amount REAL NOT NULL,
    commission REAL NOT NULL,
    lender_earnings REAL NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'BORROWED' CHECK(status IN ('BORROWED', 'RETURN_PENDING', 'COMPLETED', 'CANCELLED')),
    returned_on DATE,
    late_days INTEGER NOT NULL DEFAULT 0,
    late_fee REAL NOT NULL DEFAULT 0.0,
    return_condition VARCHAR(50) NOT NULL DEFAULT '',
    damage_charge REAL NOT NULL DEFAULT 0.0,
    FOREIGN KEY (request_id) REFERENCES borrow_requests(request_id) ON DELETE RESTRICT,
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE RESTRICT,
    FOREIGN KEY (borrower_id) REFERENCES students(student_id) ON DELETE RESTRICT,
    FOREIGN KEY (lender_id) REFERENCES students(student_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS return_records (
    return_id VARCHAR(10) PRIMARY KEY,
    transaction_id VARCHAR(10) NOT NULL,
    item_id VARCHAR(10) NOT NULL,
    borrower_id VARCHAR(10) NOT NULL,
    lender_id VARCHAR(10) NOT NULL,
    return_date DATE NOT NULL,
    return_condition VARCHAR(50) NOT NULL,
    late_days INTEGER NOT NULL DEFAULT 0,
    late_fee REAL NOT NULL DEFAULT 0.0,
    damage_charge REAL NOT NULL DEFAULT 0.0,
    status VARCHAR(20) NOT NULL DEFAULT 'RETURN_SUBMITTED' CHECK(status IN ('RETURN_SUBMITTED', 'CONFIRMED')),
    FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id) ON DELETE RESTRICT,
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE RESTRICT,
    FOREIGN KEY (borrower_id) REFERENCES students(student_id) ON DELETE RESTRICT,
    FOREIGN KEY (lender_id) REFERENCES students(student_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS cancellations (
    cancellation_id VARCHAR(10) PRIMARY KEY,
    actor_id VARCHAR(10) NOT NULL,
    request_id VARCHAR(10),
    transaction_id VARCHAR(10),
    reason TEXT NOT NULL DEFAULT '',
    stage VARCHAR(30) NOT NULL,
    cancelled_on DATE NOT NULL,
    FOREIGN KEY (actor_id) REFERENCES students(student_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS audit_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type VARCHAR(50) NOT NULL,
    transaction_id VARCHAR(10),
    request_id VARCHAR(10),
    student_id VARCHAR(10) NOT NULL,
    event_date DATE NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_items_lender ON items(lender_id);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_requests_item ON borrow_requests(item_id);
CREATE INDEX IF NOT EXISTS idx_requests_borrower ON borrow_requests(borrower_id);
CREATE INDEX IF NOT EXISTS idx_requests_status ON borrow_requests(status);
CREATE INDEX IF NOT EXISTS idx_transactions_borrower ON transactions(borrower_id);
CREATE INDEX IF NOT EXISTS idx_transactions_lender ON transactions(lender_id);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
"""


class DatabaseManager:
    """Handles all SQLite database interactions with ACID compliance and prepared statements, plus cloud sync."""

    def __init__(self, db_path: str = "borrow_app.db", enable_cloud_sync: bool = True):
        self.db_path = db_path
        self._init_db()
        self.sync_mgr = None
        if enable_cloud_sync:
            try:
                from supabase_sync import SupabaseSyncManager
                self.sync_mgr = SupabaseSyncManager()
            except Exception:
                self.sync_mgr = None

    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)
            cursor = conn.cursor()

            # Ensure pin column exists in existing databases (automatic migration)
            cursor.execute("PRAGMA table_info(students)")
            columns = [col["name"] for col in cursor.fetchall()]
            if "pin" not in columns:
                cursor.execute("ALTER TABLE students ADD COLUMN pin VARCHAR(10) NOT NULL DEFAULT ''")

            conn.commit()

    # --------------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------------
    def load_students(self) -> Dict[str, dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT student_id, name, pin FROM students ORDER BY student_id")
            return {
                row["student_id"]: {
                    "student_id": row["student_id"],
                    "name": row["name"],
                    "pin": row["pin"] if "pin" in row.keys() else "",
                }
                for row in cursor.fetchall()
            }

    def save_student(self, student_id: str, name: str, pin: str = "") -> None:
        with self.get_connection() as conn:
            conn.execute(
                """INSERT INTO students (student_id, name, pin) 
                   VALUES (?, ?, ?) 
                   ON CONFLICT(student_id) DO UPDATE SET 
                       name = excluded.name, 
                       pin = CASE WHEN excluded.pin != '' THEN excluded.pin ELSE students.pin END""",
                (student_id, name, pin),
            )
            conn.commit()
        if self.sync_mgr and self.sync_mgr.is_configured():
            self.sync_mgr.async_sync(self.sync_mgr.sync_student, student_id, name, pin)

    def is_pin_taken(self, pin: str, exclude_student_id: Optional[str] = None) -> bool:
        clean_pin = pin.strip() if pin else ""
        if not clean_pin:
            return False
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if exclude_student_id:
                cursor.execute(
                    "SELECT 1 FROM students WHERE pin = ? AND student_id != ? AND pin != '' LIMIT 1",
                    (clean_pin, exclude_student_id),
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM students WHERE pin = ? AND pin != '' LIMIT 1",
                    (clean_pin,),
                )
            return cursor.fetchone() is not None

    def save_student_pin(self, student_id: str, pin: str) -> None:
        with self.get_connection() as conn:
            conn.execute("UPDATE students SET pin = ? WHERE student_id = ?", (pin, student_id))
            conn.commit()
        if self.sync_mgr and self.sync_mgr.is_configured():
            st = self.load_students().get(student_id, {})
            name = st.get("name", "Student")
            self.sync_mgr.async_sync(self.sync_mgr.sync_student, student_id, name, pin)

    def load_items(self) -> Dict[str, dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT item_id, name, condition, rental_price_per_day, lender_id, status FROM items ORDER BY item_id"
            )
            return {
                row["item_id"]: {
                    "item_id": row["item_id"],
                    "name": row["name"],
                    "condition": row["condition"],
                    "rental_price_per_day": float(row["rental_price_per_day"]),
                    "lender_id": row["lender_id"],
                    "status": row["status"],
                }
                for row in cursor.fetchall()
            }

    def load_requests(self) -> Dict[str, dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT request_id, item_id, borrower_id, lender_id, duration_days, requested_on, status FROM borrow_requests ORDER BY request_id"
            )
            return {
                row["request_id"]: {
                    "request_id": row["request_id"],
                    "item_id": row["item_id"],
                    "borrower_id": row["borrower_id"],
                    "lender_id": row["lender_id"],
                    "duration_days": int(row["duration_days"]),
                    "requested_on": date.fromisoformat(row["requested_on"]),
                    "status": row["status"],
                }
                for row in cursor.fetchall()
            }

    def load_transactions(self) -> Dict[str, dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT transaction_id, request_id, item_id, borrower_id, lender_id,
                       start_date, due_date, duration_days, daily_rent, rental_amount,
                       commission, lender_earnings, status, returned_on, late_days,
                       late_fee, return_condition, damage_charge
                FROM transactions ORDER BY transaction_id
                """
            )
            data = {}
            for row in cursor.fetchall():
                ret_date = date.fromisoformat(row["returned_on"]) if row["returned_on"] else None
                data[row["transaction_id"]] = {
                    "transaction_id": row["transaction_id"],
                    "request_id": row["request_id"],
                    "item_id": row["item_id"],
                    "borrower_id": row["borrower_id"],
                    "lender_id": row["lender_id"],
                    "start_date": date.fromisoformat(row["start_date"]),
                    "due_date": date.fromisoformat(row["due_date"]),
                    "duration_days": int(row["duration_days"]),
                    "daily_rent": float(row["daily_rent"]),
                    "rental_amount": float(row["rental_amount"]),
                    "commission": float(row["commission"]),
                    "lender_earnings": float(row["lender_earnings"]),
                    "status": row["status"],
                    "returned_on": ret_date,
                    "late_days": int(row["late_days"]),
                    "late_fee": float(row["late_fee"]),
                    "return_condition": row["return_condition"] or "",
                    "damage_charge": float(row["damage_charge"]),
                }
            return data

    def load_returns(self) -> Dict[str, dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT return_id, transaction_id, item_id, borrower_id, lender_id,
                       return_date, return_condition, late_days, late_fee, damage_charge, status
                FROM return_records ORDER BY return_id
                """
            )
            return {
                row["return_id"]: {
                    "return_id": row["return_id"],
                    "transaction_id": row["transaction_id"],
                    "item_id": row["item_id"],
                    "borrower_id": row["borrower_id"],
                    "lender_id": row["lender_id"],
                    "return_date": date.fromisoformat(row["return_date"]),
                    "return_condition": row["return_condition"],
                    "late_days": int(row["late_days"]),
                    "late_fee": float(row["late_fee"]),
                    "damage_charge": float(row["damage_charge"]),
                    "status": row["status"],
                }
                for row in cursor.fetchall()
            }

    def load_cancellations(self) -> Dict[str, dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT cancellation_id, actor_id, request_id, transaction_id, reason, stage, cancelled_on
                FROM cancellations ORDER BY cancellation_id
                """
            )
            return {
                row["cancellation_id"]: {
                    "cancellation_id": row["cancellation_id"],
                    "actor_id": row["actor_id"],
                    "request_id": row["request_id"],
                    "transaction_id": row["transaction_id"],
                    "reason": row["reason"],
                    "stage": row["stage"],
                    "cancelled_on": date.fromisoformat(row["cancelled_on"]),
                }
                for row in cursor.fetchall()
            }

    def load_history(self) -> List[dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT event_type, transaction_id, request_id, student_id, event_date, details FROM audit_history ORDER BY history_id"
            )
            history = []
            for row in cursor.fetchall():
                entry = {
                    "type": row["event_type"],
                    "student_id": row["student_id"],
                    "date": row["event_date"],
                }
                if row["transaction_id"]:
                    entry["transaction_id"] = row["transaction_id"]
                if row["request_id"]:
                    entry["request_id"] = row["request_id"]
                if row["details"]:
                    entry["details"] = row["details"]
                history.append(entry)
            return history

    # --------------------------------------------------------
    # WRITE / MUTATION OPERATIONS (UPSERT)
    # --------------------------------------------------------
    def save_item(self, item) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO items (item_id, name, condition, rental_price_per_day, lender_id, status)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    name = excluded.name,
                    condition = excluded.condition,
                    rental_price_per_day = excluded.rental_price_per_day,
                    lender_id = excluded.lender_id,
                    status = excluded.status
                """,
                (item.item_id, item.name, item.condition, item.rental_price_per_day, item.lender_id, item.status),
            )
            conn.commit()
        if self.sync_mgr and self.sync_mgr.is_configured():
            self.sync_mgr.async_sync(
                self.sync_mgr.sync_item,
                item.item_id, item.name, item.condition, item.rental_price_per_day, item.lender_id, item.status
            )

    def update_item_status(self, item_id: str, status: str) -> None:
        with self.get_connection() as conn:
            conn.execute("UPDATE items SET status = ? WHERE item_id = ?", (status, item_id))
            conn.commit()
        if self.sync_mgr and self.sync_mgr.is_configured():
            def _sync():
                client = self.sync_mgr.get_client()
                if client:
                    client.table("items").update({"status": status}).eq("item_id", item_id).execute()
            self.sync_mgr.async_sync(_sync)

    def save_request(self, request) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO borrow_requests (request_id, item_id, borrower_id, lender_id, duration_days, requested_on, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    status = excluded.status
                """,
                (
                    request.request_id,
                    request.item_id,
                    request.borrower_id,
                    request.lender_id,
                    request.duration_days,
                    request.requested_on.isoformat(),
                    request.status,
                ),
            )
            conn.commit()
        if self.sync_mgr and self.sync_mgr.is_configured():
            self.sync_mgr.async_sync(
                self.sync_mgr.sync_borrow_request,
                request.request_id, request.item_id, request.borrower_id, request.lender_id,
                request.duration_days, request.requested_on.isoformat(), request.status
            )

    def update_request_status(self, request_id: str, status: str) -> None:
        with self.get_connection() as conn:
            conn.execute("UPDATE borrow_requests SET status = ? WHERE request_id = ?", (status, request_id))
            conn.commit()
        if self.sync_mgr and self.sync_mgr.is_configured():
            def _sync():
                client = self.sync_mgr.get_client()
                if client:
                    client.table("borrow_requests").update({"status": status}).eq("request_id", request_id).execute()
            self.sync_mgr.async_sync(_sync)

    def save_transaction(self, tx) -> None:
        with self.get_connection() as conn:
            ret_str = tx.returned_on.isoformat() if tx.returned_on else None
            conn.execute(
                """
                INSERT INTO transactions (
                    transaction_id, request_id, item_id, borrower_id, lender_id,
                    start_date, due_date, duration_days, daily_rent, rental_amount,
                    commission, lender_earnings, status, returned_on, late_days,
                    late_fee, return_condition, damage_charge
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(transaction_id) DO UPDATE SET
                    status = excluded.status,
                    returned_on = excluded.returned_on,
                    late_days = excluded.late_days,
                    late_fee = excluded.late_fee,
                    return_condition = excluded.return_condition,
                    damage_charge = excluded.damage_charge
                """,
                (
                    tx.transaction_id,
                    tx.request_id,
                    tx.item_id,
                    tx.borrower_id,
                    tx.lender_id,
                    tx.start_date.isoformat(),
                    tx.due_date.isoformat(),
                    tx.duration_days,
                    tx.daily_rent,
                    tx.rental_amount,
                    tx.commission,
                    tx.lender_earnings,
                    tx.status,
                    ret_str,
                    tx.late_days,
                    tx.late_fee,
                    tx.return_condition,
                    tx.damage_charge,
                ),
            )
            conn.commit()
        if self.sync_mgr and self.sync_mgr.is_configured():
            tx_data = {
                "transaction_id": tx.transaction_id,
                "request_id": tx.request_id,
                "item_id": tx.item_id,
                "borrower_id": tx.borrower_id,
                "lender_id": tx.lender_id,
                "start_date": tx.start_date.isoformat(),
                "due_date": tx.due_date.isoformat(),
                "duration_days": tx.duration_days,
                "daily_rent": tx.daily_rent,
                "rental_amount": tx.rental_amount,
                "commission": tx.commission,
                "lender_earnings": tx.lender_earnings,
                "status": tx.status,
                "returned_on": ret_str,
                "late_days": getattr(tx, "late_days", 0),
                "late_fee": getattr(tx, "late_fee", 0.0),
                "return_condition": getattr(tx, "return_condition", ""),
                "damage_charge": getattr(tx, "damage_charge", 0.0),
            }
            self.sync_mgr.async_sync(self.sync_mgr.sync_transaction, tx_data)

    def save_return_record(self, ret) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO return_records (
                    return_id, transaction_id, item_id, borrower_id, lender_id,
                    return_date, return_condition, late_days, late_fee, damage_charge, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(return_id) DO UPDATE SET
                    return_condition = excluded.return_condition,
                    late_days = excluded.late_days,
                    late_fee = excluded.late_fee,
                    damage_charge = excluded.damage_charge,
                    status = excluded.status
                """,
                (
                    ret.return_id,
                    ret.transaction_id,
                    ret.item_id,
                    ret.borrower_id,
                    ret.lender_id,
                    ret.return_date.isoformat(),
                    ret.return_condition,
                    ret.late_days,
                    ret.late_fee,
                    ret.damage_charge,
                    ret.status,
                ),
            )
            conn.commit()
        if self.sync_mgr and self.sync_mgr.is_configured():
            ret_data = {
                "return_id": ret.return_id,
                "transaction_id": ret.transaction_id,
                "item_id": ret.item_id,
                "borrower_id": ret.borrower_id,
                "lender_id": ret.lender_id,
                "return_date": ret.return_date.isoformat(),
                "return_condition": ret.return_condition,
                "late_days": ret.late_days,
                "late_fee": ret.late_fee,
                "damage_charge": ret.damage_charge,
                "status": ret.status,
            }
            self.sync_mgr.async_sync(self.sync_mgr.sync_return_record, ret_data)

    def update_return_status(self, return_id: str, status: str) -> None:
        with self.get_connection() as conn:
            conn.execute("UPDATE return_records SET status = ? WHERE return_id = ?", (status, return_id))
            conn.commit()
        if self.sync_mgr and self.sync_mgr.is_configured():
            def _sync():
                client = self.sync_mgr.get_client()
                if client:
                    client.table("return_records").update({"status": status}).eq("return_id", return_id).execute()
            self.sync_mgr.async_sync(_sync)

    def save_cancellation(self, cancel) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cancellations (
                    cancellation_id, actor_id, request_id, transaction_id, reason, stage, cancelled_on
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cancellation_id) DO UPDATE SET
                    reason = excluded.reason,
                    stage = excluded.stage
                """,
                (
                    cancel.cancellation_id,
                    cancel.actor_id,
                    cancel.request_id,
                    cancel.transaction_id,
                    cancel.reason,
                    cancel.stage,
                    cancel.cancelled_on.isoformat(),
                ),
            )
            conn.commit()

    def save_history(self, event: dict) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_history (event_type, transaction_id, request_id, student_id, event_date, details)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.get("type", "UNKNOWN"),
                    event.get("transaction_id"),
                    event.get("request_id"),
                    event.get("student_id", ""),
                    event.get("date", date.today().isoformat()),
                    str(event),
                ),
            )
            conn.commit()
        if self.sync_mgr and self.sync_mgr.is_configured():
            self.sync_mgr.async_sync(
                self.sync_mgr.sync_audit_history,
                event.get("type", "UNKNOWN"),
                event.get("transaction_id") or "",
                event.get("request_id") or "",
                event.get("student_id", ""),
                event.get("date", date.today().isoformat()),
                str(event),
            )

    # --------------------------------------------------------
    # RELATIONAL AUDIT & REPORT QUERIES (DBMS ENGINE)
    # --------------------------------------------------------
    def get_lender_inventory_report(self, lender_filter: Optional[str] = None) -> List[dict]:
        """
        Relational query joining students (lenders) and items.
        Returns rows where:
        - 1st column: lender_id
        - 2nd column: lender_name
        - item_id, item_name, cost_per_day, condition, status
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT 
                    s.student_id AS lender_id,
                    s.name AS lender_name,
                    i.item_id,
                    i.name AS item_name,
                    i.rental_price_per_day AS cost_per_day,
                    i.condition AS item_condition,
                    CASE 
                        WHEN t.status = 'RETURN_PENDING' THEN 'RETURN_PENDING'
                        ELSE i.status
                    END AS item_status
                FROM items i
                JOIN students s ON i.lender_id = s.student_id
                LEFT JOIN transactions t ON i.item_id = t.item_id AND t.status = 'RETURN_PENDING'
            """
            params: list = []
            if lender_filter:
                query += " WHERE s.student_id = ?"
                params.append(lender_filter)
            query += " ORDER BY s.student_id ASC, i.item_id ASC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_borrower_loans_report(self, lender_filter: Optional[str] = None) -> List[dict]:
        """
        Relational multi-table JOIN linking transactions, borrowers, lenders, and items.
        Reveals who borrowed what from a particular lender AU_ID and for how many days.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT 
                    t.transaction_id,
                    t.request_id,
                    b.student_id AS borrower_id,
                    b.name AS borrower_name,
                    l.student_id AS lender_id,
                    l.name AS lender_name,
                    i.item_id,
                    i.name AS item_name,
                    i.rental_price_per_day AS daily_rent,
                    t.duration_days,
                    t.rental_amount,
                    t.commission,
                    t.lender_earnings,
                    t.start_date,
                    t.due_date,
                    t.returned_on,
                    t.status AS transaction_status,
                    t.late_days,
                    t.late_fee,
                    t.damage_charge,
                    t.return_condition
                FROM transactions t
                JOIN students b ON t.borrower_id = b.student_id
                JOIN students l ON t.lender_id = l.student_id
                JOIN items i ON t.item_id = i.item_id
            """
            params: list = []
            if lender_filter:
                query += " WHERE l.student_id = ?"
                params.append(lender_filter)
            query += " ORDER BY l.student_id ASC, t.transaction_id ASC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_borrower_requests_report(self, lender_filter: Optional[str] = None) -> List[dict]:
        """
        Retrieves pending borrow requests awaiting approval from lenders.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT 
                    r.request_id,
                    b.student_id AS borrower_id,
                    b.name AS borrower_name,
                    l.student_id AS lender_id,
                    l.name AS lender_name,
                    i.item_id,
                    i.name AS item_name,
                    i.rental_price_per_day AS cost_per_day,
                    r.duration_days,
                    r.requested_on,
                    r.status AS request_status
                FROM borrow_requests r
                JOIN students b ON r.borrower_id = b.student_id
                JOIN students l ON r.lender_id = l.student_id
                JOIN items i ON r.item_id = i.item_id
                WHERE r.status = 'PENDING'
            """
            params: list = []
            if lender_filter:
                query += " AND l.student_id = ?"
                params.append(lender_filter)
            query += " ORDER BY l.student_id ASC, r.request_id ASC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_dbms_diagnostics(self) -> dict:
        """
        Runs SQLite diagnostics, table row statistics, and foreign-key integrity validation.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            tables = [
                "students",
                "items",
                "borrow_requests",
                "transactions",
                "return_records",
                "cancellations",
                "audit_history",
            ]
            counts = {}
            for tbl in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
                counts[tbl] = cursor.fetchone()[0]

            cursor.execute("PRAGMA integrity_check;")
            integrity_row = cursor.fetchone()
            integrity = integrity_row[0] if integrity_row else "unknown"

            cursor.execute("PRAGMA foreign_key_check;")
            fk_violations = len(cursor.fetchall())

            return {
                "counts": counts,
                "integrity": integrity,
                "fk_violations": fk_violations,
                "db_path": self.db_path,
            }

    def get_active_students_summary(self) -> dict:
        """
        Calculates truthful active user metrics:
        - registered: students who logged in and set their PIN
        - total_active: distinct students active in the system
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM students WHERE pin != '';")
            registered = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM students;")
            total_active = cursor.fetchone()[0]
            return {
                "registered": registered,
                "total_active": total_active,
            }

    # --------------------------------------------------------
    # CLOUD SYNCHRONIZATION HELPERS (SUPABASE)
    # --------------------------------------------------------
    def get_cloud_status(self) -> dict:
        """Returns cloud sync connection and configuration status."""
        if not self.sync_mgr:
            return {"configured": False, "status": "Disabled", "url": "", "masked_key": ""}
        return self.sync_mgr.get_status_summary()

    def sync_push_to_cloud(self) -> Tuple[bool, str, dict]:
        """Pushes full local database to Supabase Cloud."""
        if not self.sync_mgr:
            return False, "Cloud sync manager not available.", {}
        return self.sync_mgr.push_full_database(self)

    def prune_cloud_students(self) -> Tuple[bool, str, int]:
        """Removes empty/unused placeholder students from Supabase Cloud."""
        if not self.sync_mgr:
            return False, "Cloud sync manager not available.", 0
        return self.sync_mgr.prune_empty_students_in_cloud(self)

    def configure_cloud(self, url: str, key: str) -> Tuple[bool, str]:
        """Configures Supabase credentials and tests connection."""
        if not self.sync_mgr:
            try:
                from supabase_sync import SupabaseSyncManager
                self.sync_mgr = SupabaseSyncManager()
            except Exception as e:
                return False, f"Could not initialize cloud sync: {e}"
        return self.sync_mgr.set_credentials(url, key)

    def test_cloud_connection(self) -> Tuple[bool, str]:
        """Pings Supabase Cloud to verify connection."""
        if not self.sync_mgr:
            return False, "Cloud sync module not initialized."
        return self.sync_mgr.test_connection()

