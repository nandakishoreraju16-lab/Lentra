import os
import threading
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DEFAULT_SUPABASE_URL = "https://btkwitdwjrlmucdpaudi.supabase.co"


class SupabaseSyncManager:
    """
    Manages live bidirectional synchronization between the local SQLite database
    and the remote Supabase PostgreSQL cloud backend.
    """

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        self.url = url.strip() if url is not None else os.getenv("SUPABASE_URL", DEFAULT_SUPABASE_URL).strip()
        self.key = key.strip() if key is not None else os.getenv("SUPABASE_KEY", os.getenv("SUPABASE_ANON_KEY", "")).strip()
        self._client = None
        self._init_lock = threading.Lock()
        self._client_initialized = False

    def get_client(self):
        """Lazy loader for Supabase client."""
        if not self._client_initialized:
            with self._init_lock:
                if not self._client_initialized:
                    if self.url and self.key:
                        try:
                            from supabase import create_client
                            self._client = create_client(self.url, self.key)
                        except Exception as e:
                            self._client = None
                    self._client_initialized = True
        return self._client

    def is_configured(self) -> bool:
        """Returns True if both URL and Key are set."""
        return bool(self.url and self.key)

    def set_credentials(self, url: str, key: str, save_to_env: bool = True) -> Tuple[bool, str]:
        """Sets new credentials and optionally saves them to .env."""
        clean_url = url.strip() or DEFAULT_SUPABASE_URL
        clean_key = key.strip()
        if not clean_key:
            return False, "Supabase API key cannot be empty."

        self.url = clean_url
        self.key = clean_key
        with self._init_lock:
            self._client = None
            self._client_initialized = False

        if save_to_env:
            try:
                env_path = os.path.join(os.path.dirname(__file__), ".env")
                env_lines = []
                if os.path.exists(env_path):
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if not line.startswith("SUPABASE_URL=") and not line.startswith("SUPABASE_KEY="):
                                env_lines.append(line.rstrip("\r\n"))
                env_lines.append(f"SUPABASE_URL={self.url}")
                env_lines.append(f"SUPABASE_KEY={self.key}")
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(env_lines) + "\n")
            except Exception as e:
                return True, f"Credentials updated in memory (could not write .env: {e})"

        test_ok, test_msg = self.test_connection()
        return test_ok, test_msg

    def test_connection(self) -> Tuple[bool, str]:
        """Performs a quick heartbeat query against Supabase."""
        if not self.is_configured():
            return False, "Supabase credentials not configured. Please supply SUPABASE_KEY."
        try:
            client = self.get_client()
            if not client:
                return False, "Could not initialize Supabase client."
            # Attempt to query 1 row from students
            res = client.table("students").select("student_id").limit(1).execute()
            count = len(res.data) if hasattr(res, "data") else 0
            return True, f"Connected to Supabase ({self.url}) successfully."
        except Exception as e:
            err_str = str(e)
            if "Invalid API key" in err_str or "JWT" in err_str:
                return False, "Authentication failed: Invalid Supabase API Key (check Project Settings > API)."
            return False, f"Connection error: {err_str}"

    def get_status_summary(self) -> Dict[str, Any]:
        """Returns cloud connection status metadata for UI display."""
        configured = self.is_configured()
        masked_key = (self.key[:6] + "..." + self.key[-4:]) if len(self.key) > 10 else ("Set" if self.key else "Not Set")
        project_ref = self.url.replace("https://", "").replace(".supabase.co", "") if self.url else "unknown"
        return {
            "configured": configured,
            "url": self.url,
            "project_ref": project_ref,
            "masked_key": masked_key,
        }

    # --------------------------------------------------------
    # SAFE ASYNC DUAL-WRITE HOOKS (NON-BLOCKING)
    # --------------------------------------------------------
    def async_sync(self, target_fn, *args, **kwargs) -> None:
        """Executes a cloud synchronization task in a background daemon thread."""
        if not self.is_configured():
            return

        def _worker():
            try:
                target_fn(*args, **kwargs)
            except Exception:
                # Silently catch to avoid crashing CLI if network is down
                pass

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def sync_student(self, student_id: str, name: str, pin: str = "") -> bool:
        """Upserts a student into Supabase public.students."""
        client = self.get_client()
        if not client:
            return False
        payload = {"student_id": student_id, "name": name, "pin": pin}
        client.table("students").upsert(payload, on_conflict="student_id").execute()
        return True

    def sync_item(self, item_id: str, name: str, condition: str, rental_price_per_day: float, lender_id: str, status: str) -> bool:
        """Upserts an item into Supabase public.items."""
        client = self.get_client()
        if not client:
            return False
        payload = {
            "item_id": item_id,
            "name": name,
            "condition": condition,
            "rental_price_per_day": float(rental_price_per_day),
            "lender_id": lender_id,
            "status": status,
        }
        client.table("items").upsert(payload, on_conflict="item_id").execute()
        return True

    def sync_borrow_request(self, request_id: str, item_id: str, borrower_id: str, lender_id: str, duration_days: int, requested_on: str, status: str) -> bool:
        """Upserts a borrow request into Supabase public.borrow_requests."""
        client = self.get_client()
        if not client:
            return False
        payload = {
            "request_id": request_id,
            "item_id": item_id,
            "borrower_id": borrower_id,
            "lender_id": lender_id,
            "duration_days": int(duration_days),
            "requested_on": str(requested_on),
            "status": status,
        }
        client.table("borrow_requests").upsert(payload, on_conflict="request_id").execute()
        return True

    def sync_transaction(self, tx_data: dict) -> bool:
        """Upserts a transaction into Supabase public.transactions."""
        client = self.get_client()
        if not client:
            return False
        payload = {
            "transaction_id": tx_data["transaction_id"],
            "request_id": tx_data["request_id"],
            "item_id": tx_data["item_id"],
            "borrower_id": tx_data["borrower_id"],
            "lender_id": tx_data["lender_id"],
            "start_date": str(tx_data["start_date"]),
            "due_date": str(tx_data["due_date"]),
            "duration_days": int(tx_data["duration_days"]),
            "daily_rent": float(tx_data["daily_rent"]),
            "rental_amount": float(tx_data["rental_amount"]),
            "commission": float(tx_data["commission"]),
            "lender_earnings": float(tx_data["lender_earnings"]),
            "status": tx_data["status"],
            "returned_on": str(tx_data["returned_on"]) if tx_data.get("returned_on") else None,
            "late_days": int(tx_data.get("late_days", 0)),
            "late_fee": float(tx_data.get("late_fee", 0.0)),
            "return_condition": tx_data.get("return_condition", ""),
            "damage_charge": float(tx_data.get("damage_charge", 0.0)),
        }
        client.table("transactions").upsert(payload, on_conflict="transaction_id").execute()
        return True

    def sync_return_record(self, ret_data: dict) -> bool:
        """Upserts a return record into Supabase public.return_records."""
        client = self.get_client()
        if not client:
            return False
        payload = {
            "return_id": ret_data["return_id"],
            "transaction_id": ret_data["transaction_id"],
            "item_id": ret_data["item_id"],
            "borrower_id": ret_data["borrower_id"],
            "lender_id": ret_data["lender_id"],
            "return_date": str(ret_data["return_date"]),
            "return_condition": ret_data["return_condition"],
            "late_days": int(ret_data.get("late_days", 0)),
            "late_fee": float(ret_data.get("late_fee", 0.0)),
            "damage_charge": float(ret_data.get("damage_charge", 0.0)),
            "status": ret_data["status"],
        }
        client.table("return_records").upsert(payload, on_conflict="return_id").execute()
        return True

    def sync_audit_history(self, event_type: str, transaction_id: str, request_id: str, student_id: str, event_date: str, details: str) -> bool:
        """Inserts an audit history log into Supabase public.audit_history."""
        client = self.get_client()
        if not client:
            return False
        payload = {
            "event_type": event_type,
            "transaction_id": transaction_id or "",
            "request_id": request_id or "",
            "student_id": student_id,
            "event_date": str(event_date),
            "details": str(details),
        }
        client.table("audit_history").insert(payload).execute()
        return True

    # --------------------------------------------------------
    # FULL BATCH PUSH / PULL / PRUNE
    # --------------------------------------------------------
    def push_full_database(self, db) -> Tuple[bool, str, Dict[str, int]]:
        """
        Pushes all records currently in SQLite to Supabase Cloud in correct relational order.
        """
        if not self.is_configured():
            return False, "Supabase key not configured.", {}

        client = self.get_client()
        if not client:
            return False, "Could not initialize Supabase client.", {}

        counts = {}
        try:
            # 1. Students
            students = db.load_students()
            if students:
                st_payload = [
                    {"student_id": s["student_id"], "name": s["name"], "pin": s["pin"]}
                    for s in students.values()
                ]
                client.table("students").upsert(st_payload, on_conflict="student_id").execute()
                counts["students"] = len(st_payload)

            # 2. Items
            items = db.load_items()
            if items:
                it_payload = [
                    {
                        "item_id": i["item_id"],
                        "name": i["name"],
                        "condition": i["condition"],
                        "rental_price_per_day": float(i["rental_price_per_day"]),
                        "lender_id": i["lender_id"],
                        "status": i["status"],
                    }
                    for i in items.values()
                ]
                client.table("items").upsert(it_payload, on_conflict="item_id").execute()
                counts["items"] = len(it_payload)

            # 3. Requests
            requests = db.load_requests()
            if requests:
                req_payload = [
                    {
                        "request_id": r["request_id"],
                        "item_id": r["item_id"],
                        "borrower_id": r["borrower_id"],
                        "lender_id": r["lender_id"],
                        "duration_days": int(r["duration_days"]),
                        "requested_on": str(r["requested_on"]),
                        "status": r["status"],
                    }
                    for r in requests.values()
                ]
                client.table("borrow_requests").upsert(req_payload, on_conflict="request_id").execute()
                counts["borrow_requests"] = len(req_payload)

            # 4. Transactions
            txs = db.load_transactions()
            if txs:
                tx_payload = [
                    {
                        "transaction_id": t["transaction_id"],
                        "request_id": t["request_id"],
                        "item_id": t["item_id"],
                        "borrower_id": t["borrower_id"],
                        "lender_id": t["lender_id"],
                        "start_date": str(t["start_date"]),
                        "due_date": str(t["due_date"]),
                        "duration_days": int(t["duration_days"]),
                        "daily_rent": float(t["daily_rent"]),
                        "rental_amount": float(t["rental_amount"]),
                        "commission": float(t["commission"]),
                        "lender_earnings": float(t["lender_earnings"]),
                        "status": t["status"],
                        "returned_on": str(t["returned_on"]) if t.get("returned_on") else None,
                        "late_days": int(t.get("late_days", 0)),
                        "late_fee": float(t.get("late_fee", 0.0)),
                        "return_condition": t.get("return_condition", ""),
                        "damage_charge": float(t.get("damage_charge", 0.0)),
                    }
                    for t in txs.values()
                ]
                client.table("transactions").upsert(tx_payload, on_conflict="transaction_id").execute()
                counts["transactions"] = len(tx_payload)

            # 5. Returns
            returns = db.load_returns()
            if returns:
                ret_payload = [
                    {
                        "return_id": r["return_id"],
                        "transaction_id": r["transaction_id"],
                        "item_id": r["item_id"],
                        "borrower_id": r["borrower_id"],
                        "lender_id": r["lender_id"],
                        "return_date": str(r["return_date"]),
                        "return_condition": r["return_condition"],
                        "late_days": int(r.get("late_days", 0)),
                        "late_fee": float(r.get("late_fee", 0.0)),
                        "damage_charge": float(r.get("damage_charge", 0.0)),
                        "status": r["status"],
                    }
                    for r in returns.values()
                ]
                client.table("return_records").upsert(ret_payload, on_conflict="return_id").execute()
                counts["return_records"] = len(ret_payload)

            return True, "Successfully synchronized all local tables to Supabase Cloud!", counts
        except Exception as e:
            return False, f"Failed to push database to cloud: {e}", counts

    def prune_empty_students_in_cloud(self, db) -> Tuple[bool, str, int]:
        """
        Removes unused students with empty PINs from Supabase Cloud
        so the cloud dashboard only displays active students.
        """
        if not self.is_configured():
            return False, "Supabase key not configured.", 0

        client = self.get_client()
        if not client:
            return False, "Could not initialize Supabase client.", 0

        try:
            # Query all students in cloud
            res = client.table("students").select("student_id, pin").execute()
            rows = res.data or []
            
            # Active IDs from local SQLite
            active_ids = set(db.load_students().keys())
            
            deleted_count = 0
            for row in rows:
                sid = row["student_id"]
                pin = row.get("pin", "")
                # If pin is empty and not in active local users, delete
                if (not pin or pin == "EMPTY") and sid not in active_ids:
                    try:
                        client.table("students").delete().eq("student_id", sid).execute()
                        deleted_count += 1
                    except Exception:
                        pass

            return True, f"Pruned {deleted_count} empty placeholder student records from Supabase Cloud.", deleted_count
        except Exception as e:
            return False, f"Error pruning cloud students: {e}", 0
