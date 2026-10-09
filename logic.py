# =============================================================================
# logic.py  —  BUSINESS RULES FOR "BORROW INSTEAD OF BUY" APP
# =============================================================================
# What this file does:
#   1. Defines the DATA CLASSES (blueprints) for Student, Item, BorrowRequest,
#      Transaction, ReturnRecord, Cancellation.
#   2. Contains all the CALCULATION FUNCTIONS (rental, commission, late fee,
#      damage charge).
#   3. Has the main BorrowInsteadOfBuyApp class which handles all the actions
#      like adding items, creating borrow requests, accepting, returning etc.
#
# HOW IT CONNECTS TO OTHER FILES:
#   - database.py  : saves/loads data to the SQLite file (borrow_app.db)
#   - main.py      : calls functions here to run the menu-based interface
#   - supabase_sync.py : pushes data to the online cloud (Supabase)
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass       # dataclass = easy way to create simple data-holder classes
from datetime import date, timedelta    # date = calendar date, timedelta = difference between dates
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING  # just type hints for readability
import re                               # re = regular expressions (used for checking student ID format)

if TYPE_CHECKING:
    from database import DatabaseManager   # only imported when checking types, not at runtime


# ----- App-wide constants (fixed rates used in calculations) -----
COMMISSION_RATE      = 0.10   # The app takes 10% commission from every rental
LATE_FEE_RATE_PER_DAY = 0.20  # 20% of rental is charged per extra late day

# Damage rates: how much extra the borrower pays based on condition at return
# The value is a MULTIPLIER of the rental amount  (e.g. 0.15 = 15% extra)
DAMAGE_RATES = {
    "NO DAMAGE":      0.00,   # No extra charge
    "MINOR":          0.15,   # Pay 15% of rental as damage fee
    "MODERATE":       0.55,   # Pay 55% of rental as damage fee
    "SEVERE":         0.90,   # Pay 90% of rental as damage fee
    "COMPLETE DAMAGE": None,  # None means: handled separately (full item cost)
}


# ============================================================
# SECTION 1: CALCULATION FUNCTIONS
# Simple math functions used throughout the app
# ============================================================

def round_money(value: float) -> float:
    """
    Round a number to 2 decimal places (like money: ₹10.50).
    The tiny +1e-10 fixes a floating point issue where 0.1+0.2 = 0.30000000004.
    """
    return round(float(value) + 1e-10, 2)


def calculate_rental(daily_price: float, days: int) -> float:
    """Total rental = price per day × number of days. Example: ₹50/day × 3 days = ₹150"""
    return round_money(daily_price * days)


def calculate_commission(rental_amount: float) -> float:
    """The app earns 10% of the rental. Example: ₹100 rental → ₹10 commission."""
    return round_money(rental_amount * COMMISSION_RATE)


def calculate_lender_earnings(rental_amount: float) -> float:
    """Lender gets 90% (rental minus 10% commission). Example: ₹100 → lender gets ₹90."""
    return round_money(rental_amount - calculate_commission(rental_amount))


def calculate_late_fee(rental_amount: float, late_days: int) -> float:
    """
    If item is returned late, charge 20% of rental per extra day.
    max(late_days, 0) makes sure we never get a negative fee.
    Example: ₹100 rental, 2 days late → 100 × 0.20 × 2 = ₹40 late fee.
    """
    return round_money(rental_amount * LATE_FEE_RATE_PER_DAY * max(late_days, 0))


def calculate_damage_charge(rental_amount: float, condition: str) -> Optional[float]:
    """
    Calculate the extra charge based on how damaged the item is.
    Returns None for COMPLETE DAMAGE (handled separately).
    Example: MINOR damage on ₹100 rental → ₹100 × 0.15 = ₹15 damage charge.
    """
    # First, convert condition text to a standard format (e.g. "minor damage" → "MINOR")
    normalized = normalize_condition(condition)
    # Look up the damage rate (a multiplier like 0.15 for MINOR)
    rate = DAMAGE_RATES.get(normalized)
    if rate is None:      # COMPLETE DAMAGE has no automatic rate
        return None
    return round_money(rental_amount * rate)


def normalize_condition(condition: str) -> str:
    """
    Convert any way a user might type the condition into a standard keyword.
    Example: "minor damage", "Minor", "MINOR DAMAGE" all become "MINOR".
    This way the rest of the code always works with clean, consistent values.
    """
    # Dictionary maps all possible spellings → one official keyword
    aliases = {
        "GOOD":           "NO DAMAGE",
        "NO DAMAGE":      "NO DAMAGE",
        "MINOR DAMAGE":   "MINOR",
        "MINOR":          "MINOR",
        "MODERATE DAMAGE":"MODERATE",
        "MODERATE":       "MODERATE",
        "MAJOR DAMAGE":   "SEVERE",
        "SEVERE DAMAGE":  "SEVERE",
        "SEVERE":         "SEVERE",
        "COMPLETE DAMAGE":"COMPLETE DAMAGE",
    }
    # .strip() removes spaces, .upper() converts to UPPERCASE, then we look it up
    return aliases.get(condition.strip().upper(), condition.strip().upper())


def validate_student_id(student_id: str) -> Tuple[bool, str]:
    """
    Check if a Student ID is in the correct format: AU25UG001 to AU25UG100.
    Returns a tuple: (True/False, the cleaned ID or an error message).
    """
    if student_id is None:
        return False, "Student ID is required."

    normalized = student_id.strip().upper()   # remove spaces and convert to uppercase
    if not normalized:
        return False, "Student ID is required."

    # re.fullmatch checks if the ID exactly matches the pattern AU25UG followed by 3 digits
    match = re.fullmatch(r"AU25UG(\d{3})", normalized)
    if not match:
        return False, "Invalid Student ID. Use AU25UG001 to AU25UG100."

    number = int(match.group(1))   # extract the 3-digit number (e.g. "007" → 7)
    if not 1 <= number <= 100:
        return False, "Invalid Student ID. The last three digits must be 001 to 100."

    return True, normalized   # all good — return the clean uppercase ID


def parse_positive_float(value: str) -> Optional[float]:
    """
    Try to convert a string to a positive decimal number.
    Returns the number if successful, or None if it fails or is zero/negative.
    Example: "50.5" → 50.5,   "abc" → None,   "-10" → None.
    """
    try:
        number = float(value.strip())
        return number if number > 0 else None   # reject zero and negative numbers
    except (ValueError, AttributeError):
        return None   # if conversion fails (e.g. letters typed), return None


def parse_positive_int(value: str) -> Optional[int]:
    """
    Try to convert a string to a positive whole number.
    Returns the number if successful, or None if it fails.
    Example: "3" → 3,   "0" → None,   "abc" → None.
    """
    try:
        number = int(value.strip())
        return number if number > 0 else None
    except (ValueError, AttributeError):
        return None


# ============================================================
# SECTION 2: DATA CLASSES (Blueprints / Templates for our data)
# ============================================================
# A @dataclass is a quick way to create a class that just holds data.
# Python automatically gives it __init__ so you can do Student(id, name, pin).
# Think of each class like a row in a database table.

@dataclass
class Student:
    """Represents one student. Every student has an ID, name, and optional PIN."""
    student_id: str   # e.g. "AU25UG007"
    name: str         # e.g. "Ravi Kumar"
    pin: str = ""     # 4-digit security PIN (empty = not set yet)


@dataclass
class Item:
    """Represents one item listed for lending (e.g. a calculator or lab coat)."""
    item_id: str                  # auto-generated e.g. "I001"
    name: str                     # e.g. "Casio Calculator"
    condition: str                # e.g. "★★★★★ Pristine"
    rental_price_per_day: float   # e.g. 50.0 means ₹50 per day
    lender_id: str                # the student who owns and listed this item
    status: str = "AVAILABLE"     # AVAILABLE / BORROWED / RETURN_PENDING


@dataclass
class BorrowRequest:
    """Created when a borrower asks to borrow an item. Lender must accept/reject it."""
    request_id: str       # auto-generated e.g. "R001"
    item_id: str          # which item is being requested
    borrower_id: str      # who wants to borrow it
    lender_id: str        # who owns the item
    duration_days: int    # how many days they want to borrow
    requested_on: date    # the date the request was made
    status: str = "PENDING"  # PENDING / ACCEPTED / REJECTED / CANCELLED


@dataclass
class Transaction:
    """
    Created when a lender ACCEPTS a borrow request.
    Tracks the full lifecycle: start date, due date, rental amount, late fee, damage.
    """
    transaction_id: str      # e.g. "T001"
    request_id: str          # which request this came from
    item_id: str             # which item is being borrowed
    borrower_id: str         # who borrowed it
    lender_id: str           # who lent it
    start_date: date         # when borrowing started
    due_date: date           # when it must be returned
    duration_days: int       # total days agreed
    daily_rent: float        # price per day
    rental_amount: float     # total rental = daily_rent × duration_days
    commission: float        # app's 10% cut
    lender_earnings: float   # lender gets 90%
    status: str = "BORROWED"        # BORROWED / RETURN_PENDING / COMPLETED / CANCELLED
    returned_on: Optional[date] = None  # date it was actually returned (None = not yet)
    late_days: int = 0       # how many days overdue
    late_fee: float = 0.0    # extra charge for being late
    return_condition: str = ""   # condition when returned (e.g. "MINOR")
    damage_charge: float = 0.0   # extra charge for damage


@dataclass
class ReturnRecord:
    """
    Created when a borrower submits a return.
    Holds condition + charges. Lender must confirm it to complete the transaction.
    """
    return_id: str          # e.g. "RET001"
    transaction_id: str     # which transaction this return belongs to
    item_id: str
    borrower_id: str
    lender_id: str
    return_date: date       # date the borrower said they returned it
    return_condition: str   # e.g. "NO DAMAGE", "MINOR", "MODERATE"
    late_days: int
    late_fee: float
    damage_charge: float
    status: str = "RETURN_SUBMITTED"  # RETURN_SUBMITTED / CONFIRMED


@dataclass
class Cancellation:
    """Records whenever a request or transaction is cancelled."""
    cancellation_id: str
    actor_id: str              # who cancelled it
    request_id: Optional[str]      # set if a request was cancelled
    transaction_id: Optional[str]  # set if a booking/transaction was cancelled
    reason: str
    stage: str
    cancelled_on: date


# ============================================================
# SECTION 3: MAIN APP CLASS
# This is the heart of the application.
# All actions (add item, borrow, return, cancel) are methods here.
# ============================================================

class BorrowInsteadOfBuyApp:
    """
    The main application class.
    It stores all students, items, requests, transactions and returns in memory.
    If a db_path is given, it also saves/loads everything to an SQLite database file.
    """

    def __init__(self, today: Optional[date] = None, db_path: Optional[str] = None):
        """
        Set up the app when it starts.
        - today: the current date (defaults to today's real date)
        - db_path: path to the SQLite database file (e.g. "borrow_app.db")
        """
        # Use today's real date unless a custom date is passed (useful for testing)
        self.today = today or date.today()
        self.db_path = db_path
        self.db = None   # will hold the database connection if db_path is given

        # If a database path is provided, connect to it
        if self.db_path:
            from database import DatabaseManager
            self.db = DatabaseManager(self.db_path)

        # In-memory dictionaries: key = ID string, value = data object
        # These act like tables in a database but stored in RAM for fast access
        self.students: Dict[str, Student] = {}          # all 100 campus students
        self.items: Dict[str, Item] = {}                # all listed items
        self.requests: Dict[str, BorrowRequest] = {}    # all borrow requests
        self.transactions: Dict[str, Transaction] = {}  # all active/completed loans
        self.returns: Dict[str, ReturnRecord] = {}      # all return records
        self.cancellations: Dict[str, Cancellation] = {} # all cancellation records
        self.history: List[dict] = []                   # full activity log

        # Counters for generating unique IDs (R001, T001, RET001 etc.)
        self._request_counter = 1
        self._transaction_counter = 1
        self._return_counter = 1
        self._cancellation_counter = 1

        # Seed the 100 students (AU25UG001 to AU25UG100) into self.students
        self._seed_students()

        # If database exists, load all saved data into memory
        if self.db:
            self._load_from_db()

    def _load_from_db(self) -> None:
        if not self.db:
            return

        # Load students from DB
        students_data = self.db.load_students()
        for sid, s in students_data.items():
            self.students[sid] = Student(
                student_id=s["student_id"],
                name=s["name"],
                pin=s.get("pin", ""),
            )

        # Load items
        items_data = self.db.load_items()
        for iid, i in items_data.items():
            self.items[iid] = Item(
                item_id=i["item_id"],
                name=i["name"],
                condition=i["condition"],
                rental_price_per_day=i["rental_price_per_day"],
                lender_id=i["lender_id"],
                status=i["status"],
            )

        # Load requests
        requests_data = self.db.load_requests()
        for rid, r in requests_data.items():
            self.requests[rid] = BorrowRequest(
                request_id=r["request_id"],
                item_id=r["item_id"],
                borrower_id=r["borrower_id"],
                lender_id=r["lender_id"],
                duration_days=r["duration_days"],
                requested_on=r["requested_on"],
                status=r["status"],
            )
            num = int(rid[1:]) if rid.startswith("R") and rid[1:].isdigit() else 0
            self._request_counter = max(self._request_counter, num + 1)

        # Load transactions
        tx_data = self.db.load_transactions()
        for tid, t in tx_data.items():
            self.transactions[tid] = Transaction(
                transaction_id=t["transaction_id"],
                request_id=t["request_id"],
                item_id=t["item_id"],
                borrower_id=t["borrower_id"],
                lender_id=t["lender_id"],
                start_date=t["start_date"],
                due_date=t["due_date"],
                duration_days=t["duration_days"],
                daily_rent=t["daily_rent"],
                rental_amount=t["rental_amount"],
                commission=t["commission"],
                lender_earnings=t["lender_earnings"],
                status=t["status"],
                returned_on=t["returned_on"],
                late_days=t["late_days"],
                late_fee=t["late_fee"],
                return_condition=t["return_condition"],
                damage_charge=t["damage_charge"],
            )
            num = int(tid[1:]) if tid.startswith("T") and tid[1:].isdigit() else 0
            self._transaction_counter = max(self._transaction_counter, num + 1)

        # Load returns
        returns_data = self.db.load_returns()
        for ret_id, ret in returns_data.items():
            self.returns[ret_id] = ReturnRecord(
                return_id=ret["return_id"],
                transaction_id=ret["transaction_id"],
                item_id=ret["item_id"],
                borrower_id=ret["borrower_id"],
                lender_id=ret["lender_id"],
                return_date=ret["return_date"],
                return_condition=ret["return_condition"],
                late_days=ret["late_days"],
                late_fee=ret["late_fee"],
                damage_charge=ret["damage_charge"],
                status=ret["status"],
            )
            num = int(ret_id.replace("RET", "")) if ret_id.startswith("RET") and ret_id[3:].isdigit() else 0
            self._return_counter = max(self._return_counter, num + 1)

        # Load cancellations
        cancellations_data = self.db.load_cancellations()
        for cid, c in cancellations_data.items():
            self.cancellations[cid] = Cancellation(
                cancellation_id=c["cancellation_id"],
                actor_id=c["actor_id"],
                request_id=c["request_id"],
                transaction_id=c["transaction_id"],
                reason=c["reason"],
                stage=c["stage"],
                cancelled_on=c["cancelled_on"],
            )
            num = int(cid[1:]) if cid.startswith("C") and cid[1:].isdigit() else 0
            self._cancellation_counter = max(self._cancellation_counter, num + 1)

        # Load history
        self.history = self.db.load_history()

    # ========================================================
    # SECTION 4: ID GENERATORS (Create unique IDs like I001, R001)
    # ========================================================

    def _next_item_id(self) -> str:
        """
        Generate the next available Item ID (e.g. 'I001', 'I002').
        Loops starting from 1 until it finds an unused number.
        The user never has to type an item ID — it's automatic!
        """
        number = 1
        while f"I{number:03d}" in self.items:
            number += 1
        return f"I{number:03d}"

    def _next_request_id(self) -> str:
        """Generate the next Borrow Request ID (e.g. 'R001', 'R002')."""
        value = f"R{self._request_counter:03d}"
        self._request_counter += 1
        return value

    def _next_transaction_id(self) -> str:
        """Generate the next Transaction ID (e.g. 'T001', 'T002')."""
        value = f"T{self._transaction_counter:03d}"
        self._transaction_counter += 1
        return value

    def _next_return_id(self) -> str:
        """Generate the next Return Record ID (e.g. 'RET001', 'RET002')."""
        value = f"RET{self._return_counter:03d}"
        self._return_counter += 1
        return value

    def _next_cancellation_id(self) -> str:
        """Generate the next Cancellation ID (e.g. 'C001', 'C002')."""
        value = f"C{self._cancellation_counter:03d}"
        self._cancellation_counter += 1
        return value

    # ========================================================
    # SECTION 5: STUDENT AUTHENTICATION & SECURITY PINs
    # ========================================================

    def _seed_students(self) -> None:
        """
        Pre-populates the 100 campus students (AU25UG001 to AU25UG100)
        with default names into memory when the app starts.
        """
        for number in range(1, 101):
            student_id = f"AU25UG{number:03d}"
            self.students[student_id] = Student(student_id, f"Student {number:03d}")

    def verify_student_id(self, student_id: str) -> Tuple[bool, str]:
        """
        Check if a Student ID is valid and exists in our directory.
        Returns: (True, "AU25UG007") on success, or (False, "Error message") on failure.
        """
        ok, normalized = validate_student_id(student_id)
        if not ok:
            return False, normalized
        if normalized not in self.students:
            return False, "Unknown Student ID."
        return True, normalized

    def normalize_student_input(self, input_val: str) -> Tuple[bool, str]:
        """
        User-friendly login helper:
        Accepts EITHER full ID (e.g. 'AU25UG007') OR shorthand roll number (e.g. '7' or '07').
        Automatically converts '7' -> 'AU25UG007'.
        """
        if not input_val or not input_val.strip():
            return False, "Student ID or Roll No is required."
        val = input_val.strip().upper()
        # If user just typed numbers (e.g. "7" or "025")
        if val.isdigit():
            num = int(val)
            if 1 <= num <= 100:
                return self.verify_student_id(f"AU25UG{num:03d}")
            return False, "Roll number must be between 1 and 100."
        # Otherwise validate full ID string
        return self.verify_student_id(val)

    def get_student_pin(self, student_id: str) -> str:
        """Return the 4-digit security PIN for a student (empty string if not yet set)."""
        student = self.students.get(student_id)
        return student.pin if student else ""

    def is_pin_taken(self, pin: str, exclude_student_id: Optional[str] = None) -> bool:
        """
        Check if a PIN is already being used by another student.
        Each student must have a UNIQUE 4-digit PIN for security.
        """
        clean_pin = pin.strip() if pin else ""
        if not clean_pin:
            return False
        # Check in-memory registered students
        for sid, s in self.students.items():
            if sid != exclude_student_id and s.pin and s.pin == clean_pin:
                return True
        # Check SQLite DB if attached
        if self.db:
            return self.db.is_pin_taken(clean_pin, exclude_student_id)
        return False

    def set_student_pin(self, student_id: str, pin: str) -> Tuple[bool, str]:
        """
        Set or update a student's 4-digit security PIN.
        Checks:
          1. Student ID is valid
          2. PIN is exactly 4 digits (e.g. '1234')
          3. PIN is not already chosen by another student
        Saves to memory and persists to SQLite database.
        """
        ok, sid = self.verify_student_id(student_id)
        if not ok:
            return False, sid
        clean_pin = pin.strip()
        if len(clean_pin) != 4 or not clean_pin.isdigit():
            return False, "PIN must be exactly 4 numeric digits (e.g. 1234)."
        if self.is_pin_taken(clean_pin, exclude_student_id=sid):
            return False, "The PIN is already used. Please choose a different PIN."
        student = self.students.get(sid)
        name = student.name if student else (f"Student {sid[6:]}" if sid.startswith("AU25UG") else "Student")
        if sid not in self.students:
            self.students[sid] = Student(sid, name, clean_pin)
        else:
            self.students[sid].pin = clean_pin

        if self.db:
            self.db.save_student(sid, name, clean_pin)
        return True, "PIN set successfully."

    def verify_student_pin(self, student_id: str, pin: str) -> bool:
        """
        Check if entered PIN matches the student's saved PIN.
        Returns True if correct, False if wrong.
        """
        student = self.students.get(student_id)
        if not student:
            return False
        return student.pin == pin.strip()

    # ========================================================
    # SECTION 6: ITEM MANAGEMENT (Lending & Searching)
    # ========================================================

    def add_item(
        self,
        lender_id: str,
        name: str,
        condition: str,
        rental_price_per_day: float,
    ) -> Tuple[bool, str]:
        """
        Add a new item to be lent out by a student.
        Steps:
          1. Verify lender's student ID (e.g. 'AU25UG007').
          2. Check that name is not empty or purely numeric.
          3. Check that condition is selected.
          4. Check that daily price is positive (> ₹0).
          5. Generate a unique Item ID (e.g. 'I001').
          6. Save to memory and write to SQLite database.
        Returns: (True, item_id) on success, or (False, error_message) on failure.
        """
        # Step 1: Validate lender ID
        ok, lender = self.verify_student_id(lender_id)
        if not ok:
            return False, lender

        # Step 2: Validate item fields
        if not name.strip():
            return False, "Item name is required."
        if name.strip().isdigit():
            return False, "Item name cannot be purely numbers. Please enter a descriptive item name."
        if not condition.strip():
            return False, "Item condition is required."
        if rental_price_per_day <= 0:
            return False, "Daily rental price must be positive."

        # Step 3: Generate next unique ID and create the Item object
        item_id = self._next_item_id()
        item = Item(
            item_id=item_id,
            name=name.strip(),
            condition=condition.strip(),
            rental_price_per_day=round_money(rental_price_per_day),
            lender_id=lender,
        )
        self.items[item_id] = item

        # Step 4: Persist to local SQLite database if attached
        if self.db:
            stu = self.students.get(lender)
            stu_name = stu.name if stu else (f"Student {lender[6:]}" if lender.startswith("AU25UG") else "Student")
            stu_pin = stu.pin if stu else ""
            self.db.save_student(lender, stu_name, stu_pin)
            self.db.save_item(item)

        return True, item_id

    def get_lender_items(self, lender_id: str) -> List[Item]:
        """Return a list of all items listed by a specific lender student."""
        return [item for item in self.items.values() if item.lender_id == lender_id]

    def search_items(self, required_item: str = "") -> List[Item]:
        """
        Find and return all items available to borrow.
        Filters by status == 'AVAILABLE'.
        If 'required_item' keyword is given, searches matching names and conditions.
        Results are sorted by item ID for clean presentation.
        """
        term = required_item.strip().lower()
        return sorted(
            [
                item
                for item in self.items.values()
                if item.status == "AVAILABLE"
                and (not term or term in item.name.lower() or term in item.condition.lower())
            ],
            key=lambda item: item.item_id,
        )

    # ========================================================
    # SECTION 7: BORROW REQUESTS & ACCEPTANCE WORKFLOW
    # ========================================================

    def create_borrow_request(
        self, borrower_id: str, item_id: str, duration_days: int
    ) -> Tuple[bool, str]:
        """
        Create a new request to borrow an item for X days.
        Steps:
          1. Check borrower student ID exists.
          2. Check item exists and is currently 'AVAILABLE'.
          3. Prevent lender from borrowing their own item.
          4. Prevent duplicate requests if a request is already pending.
          5. Generate Request ID (e.g. 'R001') and mark item as 'REQUESTED'.
        Returns: (True, request_id) or (False, error_message).
        """
        # Step 1: Check borrower ID
        ok, borrower = self.verify_student_id(borrower_id)
        if not ok:
            return False, borrower
        if item_id not in self.items:
            return False, "Item not found."
        if not isinstance(duration_days, int) or duration_days <= 0:
            return False, "Borrowing duration must be a positive whole number."

        # Step 2: Check item availability and ownership
        item = self.items[item_id]
        if item.lender_id == borrower:
            return False, "You cannot borrow your own item."
        if item.status != "AVAILABLE":
            return False, "Item is not available."
        if any(
            request.item_id == item_id and request.status == "PENDING"
            for request in self.requests.values()
        ):
            return False, "A pending request already exists for this item."

        request = BorrowRequest(
            request_id=self._next_request_id(),
            item_id=item.item_id,
            borrower_id=borrower,
            lender_id=item.lender_id,
            duration_days=duration_days,
            requested_on=self.today,
        )
        self.requests[request.request_id] = request
        item.status = "REQUESTED"

        if self.db:
            stu = self.students.get(borrower)
            stu_name = stu.name if stu else (f"Student {borrower[6:]}" if borrower.startswith("AU25UG") else "Student")
            stu_pin = stu.pin if stu else ""
            self.db.save_student(borrower, stu_name, stu_pin)
            self.db.save_request(request)
            self.db.update_item_status(item.item_id, item.status)

        return True, request.request_id

    def get_pending_return_for_item(self, item_id: str) -> Optional[ReturnRecord]:
        """Check if an item has a return record waiting for lender confirmation."""
        for return_record in self.returns.values():
            if return_record.item_id == item_id and return_record.status == "RETURN_SUBMITTED":
                return return_record
        return None

    def accept_request(
        self, lender_id: str, request_id: str, start_date: Optional[date] = None
    ) -> Tuple[bool, str]:
        """
        Lender accepts a pending borrow request.
        Steps:
          1. Check lender student ID is valid.
          2. Check the request exists, belongs to this lender, and is 'PENDING'.
          3. Calculate rental amount (daily_rent * days), commission (10%), lender earnings (90%).
          4. Create a Transaction (e.g. 'T001') with start_date and due_date.
          5. Update request status to 'ACCEPTED' and item status to 'BORROWED'.
          6. Save to local SQLite database.
        Returns: (True, transaction_id) on success, or (False, error_message).
        """
        # Step 1: Validate lender ID
        ok, lender = self.verify_student_id(lender_id)
        if not ok:
            return False, lender

        # Step 2: Validate request status
        request = self.requests.get(request_id)
        if not request or request.lender_id != lender:
            return False, "Borrow request not found for this lender."
        if request.status != "PENDING":
            return False, "This request is no longer pending."

        item = self.items.get(request.item_id)
        if not item or item.status != "REQUESTED":
            return False, "Item is no longer available for this request."

        # Step 3: Financial calculations
        start = start_date or self.today
        rental_amount = calculate_rental(item.rental_price_per_day, request.duration_days)
        commission = calculate_commission(rental_amount)
        lender_earnings = calculate_lender_earnings(rental_amount)

        # Step 4: Create new Transaction record
        request.status = "ACCEPTED"
        transaction = Transaction(
            transaction_id=self._next_transaction_id(),
            request_id=request.request_id,
            item_id=item.item_id,
            borrower_id=request.borrower_id,
            lender_id=request.lender_id,
            start_date=start,
            due_date=start + timedelta(days=request.duration_days),
            duration_days=request.duration_days,
            daily_rent=item.rental_price_per_day,
            rental_amount=rental_amount,
            commission=commission,
            lender_earnings=lender_earnings,
        )
        self.transactions[transaction.transaction_id] = transaction
        item.status = "BORROWED"

        # Step 5: Log to activity history
        history_entry = {
            "type": "BORROWING_STARTED",
            "transaction_id": transaction.transaction_id,
            "student_id": transaction.borrower_id,
            "date": start.isoformat(),
        }
        self.history.append(history_entry)

        # Step 6: Persist updates to SQLite database
        if self.db:
            self.db.update_request_status(request.request_id, request.status)
            self.db.save_transaction(transaction)
            self.db.update_item_status(item.item_id, item.status)
            self.db.save_history(history_entry)

        return True, transaction.transaction_id

    def reject_request(self, lender_id: str, request_id: str) -> Tuple[bool, str]:
        """
        Lender rejects a borrow request.
        Marks request as 'REJECTED' and resets item back to 'AVAILABLE'.
        """
        ok, lender = self.verify_student_id(lender_id)
        if not ok:
            return False, lender

        request = self.requests.get(request_id)
        if not request or request.lender_id != lender:
            return False, "Borrow request not found for this lender."
        if request.status != "PENDING":
            return False, "This request is no longer pending."

        # Mark rejected and make item available again
        request.status = "REJECTED"
        item = self.items.get(request.item_id)
        if item:
            item.status = "AVAILABLE"

        if self.db:
            self.db.update_request_status(request.request_id, request.status)
            if item:
                self.db.update_item_status(item.item_id, item.status)

        return True, "Borrow request rejected. Item is available again."

    # ========================================================
    # SECTION 8: ITEM RETURN & DAMAGE SETTLEMENT
    # ========================================================

    def get_active_borrowings(self, borrower_id: str) -> List[Transaction]:
        """Return all active loans (status == 'BORROWED') for this student."""
        return [
            transaction
            for transaction in self.transactions.values()
            if transaction.borrower_id == borrower_id and transaction.status == "BORROWED"
        ]

    def return_item(
        self,
        borrower_id: str,
        transaction_id: str,
        condition: str,
        return_date: Optional[date] = None,
    ) -> Tuple[bool, str]:
        """
        Borrower initiates return of a borrowed item.
        Steps:
          1. Verify borrower ID and active borrowing transaction.
          2. Calculate late days (if return_date is past due_date).
          3. Calculate late fee (20% of rental per late day).
          4. Calculate damage charge (15% for Minor, 55% for Moderate, 90% for Severe).
          5. Update transaction status to 'RETURN_PENDING'.
          6. Create ReturnRecord (e.g. 'RET001') for lender confirmation.
        Returns: (True, return_id) on success, or (False, error_message).
        """
        # Step 1: Verify borrower and transaction
        ok, borrower = self.verify_student_id(borrower_id)
        if not ok:
            return False, borrower

        transaction = self.transactions.get(transaction_id)
        if not transaction or transaction.borrower_id != borrower:
            return False, "Active borrowing not found for this borrower."
        if transaction.status != "BORROWED":
            return False, "This transaction is not active."

        # Step 2: Validate condition
        normalized = normalize_condition(condition)
        if normalized not in DAMAGE_RATES:
            return False, "Invalid return condition. Choose No Damage, Minor Damage, Moderate Damage, Severe Damage, or Complete Damage."

        # Step 3: Compute late fees and damage charges
        return_day = return_date or self.today
        late_days = max((return_day - transaction.due_date).days, 0)
        late_fee = calculate_late_fee(transaction.rental_amount, late_days)
        damage_charge = calculate_damage_charge(transaction.rental_amount, normalized)
        if normalized == "COMPLETE DAMAGE":
            damage_charge = 0.0

        # Step 4: Record details onto transaction
        transaction.returned_on = return_day
        transaction.late_days = late_days
        transaction.late_fee = late_fee
        transaction.return_condition = normalized
        transaction.damage_charge = damage_charge
        transaction.status = "RETURN_PENDING"

        record = ReturnRecord(
            return_id=self._next_return_id(),
            transaction_id=transaction.transaction_id,
            item_id=transaction.item_id,
            borrower_id=transaction.borrower_id,
            lender_id=transaction.lender_id,
            return_date=return_day,
            return_condition=normalized,
            late_days=late_days,
            late_fee=late_fee,
            damage_charge=damage_charge,
        )
        self.returns[record.return_id] = record

        if self.db:
            self.db.save_transaction(transaction)
            self.db.save_return_record(record)

        if normalized == "COMPLETE DAMAGE":
            return True, (
                f"Consult the {transaction.lender_id} lender for further consequences. "
                "Pay the full amount of the item to the lender."
            )

        return True, record.return_id

    def confirm_return(self, lender_id: str, return_id: str) -> Tuple[bool, str]:
        """
        Lender confirms receipt and condition of returned item.
        Steps:
          1. Verify lender owns the item.
          2. Check ReturnRecord exists and status is 'RETURN_SUBMITTED'.
          3. Mark ReturnRecord as 'CONFIRMED'.
          4. Mark Transaction as 'COMPLETED'.
          5. Reset Item status back to 'AVAILABLE' for other students.
          6. Persist changes to SQLite database.
        Returns: (True, success_message) or (False, error_message).
        """
        # Step 1: Validate lender ID
        ok, lender = self.verify_student_id(lender_id)
        if not ok:
            return False, lender

        # Step 2: Validate return record
        record = self.returns.get(return_id)
        if not record or record.lender_id != lender:
            return False, "Return record not found for this lender."
        if record.status != "RETURN_SUBMITTED":
            return False, "This return is no longer pending."

        transaction = self.transactions.get(record.transaction_id)
        item = self.items.get(record.item_id)
        if not transaction or not item:
            return False, "Return record is incomplete."
        if record.return_condition == "COMPLETE DAMAGE":
            return False, "Complete damage is handled outside the application."

        # Step 3: Complete transaction and release item
        record.status = "CONFIRMED"
        transaction.status = "COMPLETED"
        item.status = "AVAILABLE"

        # Step 4: Log completion to activity history
        history_entry = {
            "type": "ITEM_RETURNED",
            "transaction_id": transaction.transaction_id,
            "student_id": transaction.borrower_id,
            "date": record.return_date.isoformat(),
            "condition": record.return_condition,
            "late_days": record.late_days,
            "late_fee": record.late_fee,
            "damage_charge": record.damage_charge,
        }
        self.history.append(history_entry)

        # Step 5: Save to SQLite database
        if self.db:
            self.db.update_return_status(record.return_id, record.status)
            self.db.save_transaction(transaction)
            self.db.update_item_status(item.item_id, item.status)
            self.db.save_history(history_entry)

        return True, "Return confirmed. Transaction completed and item is available again."

    def settle_complete_damage(self, lender_id: str, return_id: str) -> Tuple[bool, str]:
        """
        Lender confirms full compensation / replacement settlement for a COMPLETE DAMAGE return.
        Transitions the return to 'CONFIRMED', transaction to 'COMPLETED', and item to 'AVAILABLE'.
        """
        ok, lender = self.verify_student_id(lender_id)
        if not ok:
            return False, lender

        record = self.returns.get(return_id)
        if not record or record.lender_id != lender:
            return False, "Return record not found for this lender."
        if record.status != "RETURN_SUBMITTED":
            return False, "This return is no longer pending."
        if record.return_condition != "COMPLETE DAMAGE":
            return False, "This action is only for Complete Damage returns."

        transaction = self.transactions.get(record.transaction_id)
        item = self.items.get(record.item_id)
        if not transaction or not item:
            return False, "Return record is incomplete."

        # Mark confirmed & completed
        record.status = "CONFIRMED"
        transaction.status = "COMPLETED"
        item.status = "AVAILABLE"

        history_entry = {
            "type": "DAMAGE_COMPENSATION_SETTLED",
            "transaction_id": transaction.transaction_id,
            "student_id": transaction.borrower_id,
            "lender_id": lender,
            "date": record.return_date.isoformat(),
            "condition": record.return_condition,
            "note": "Full damage compensation settled outside application and confirmed by lender.",
        }
        self.history.append(history_entry)

        if self.db:
            self.db.update_return_status(record.return_id, record.status)
            self.db.save_transaction(transaction)
            self.db.update_item_status(item.item_id, item.status)
            self.db.save_history(history_entry)

        return True, "Full compensation confirmed! Transaction marked as completed and item is now available."

    # ========================================================
    # SECTION 9: CANCELLATIONS (Requests & Bookings)
    # ========================================================

    def cancel_request_or_booking(
        self, student_id: str, record_id: str, reason: str = ""
    ) -> Tuple[bool, str]:
        """
        Cancel either a pending request or an accepted booking.
        Case 1: PENDING REQUEST -> cancels request, item resets to 'AVAILABLE'.
        Case 2: ACCEPTED BOOKING -> cancels loan transaction, item resets to 'AVAILABLE'.
        """
        ok, student = self.verify_student_id(student_id)
        if not ok:
            return False, student

        # Case 1: Cancel a pending borrow request
        request = self.requests.get(record_id)
        if request and request.borrower_id == student and request.status == "PENDING":
            request.status = "CANCELLED"
            item = self.items.get(request.item_id)
            if item:
                item.status = "AVAILABLE"
            cancellation = Cancellation(
                cancellation_id=self._next_cancellation_id(),
                actor_id=student,
                request_id=request.request_id,
                transaction_id=None,
                reason=reason.strip(),
                stage="PENDING_REQUEST",
                cancelled_on=self.today,
            )
            self.cancellations[cancellation.cancellation_id] = cancellation
            history_entry = {
                "type": "REQUEST_CANCELLED",
                "request_id": request.request_id,
                "student_id": student,
                "date": self.today.isoformat(),
            }
            self.history.append(history_entry)

            if self.db:
                self.db.update_request_status(request.request_id, request.status)
                if item:
                    self.db.update_item_status(item.item_id, item.status)
                self.db.save_cancellation(cancellation)
                self.db.save_history(history_entry)

            return True, "Borrow request cancelled. Item is available again."

        transaction = self.transactions.get(record_id)
        if transaction and transaction.borrower_id == student:
            if transaction.status != "BORROWED":
                return False, "This transaction is not cancellable at the current stage."

            transaction.status = "CANCELLED"
            item = self.items.get(transaction.item_id)
            if item:
                item.status = "AVAILABLE"
            request = self.requests.get(transaction.request_id)
            if request:
                request.status = "CANCELLED"

            cancellation = Cancellation(
                cancellation_id=self._next_cancellation_id(),
                actor_id=student,
                request_id=transaction.request_id,
                transaction_id=transaction.transaction_id,
                reason=reason.strip(),
                stage="ACCEPTED_BOOKING",
                cancelled_on=self.today,
            )
            self.cancellations[cancellation.cancellation_id] = cancellation
            history_entry = {
                "type": "BOOKING_CANCELLED",
                "transaction_id": transaction.transaction_id,
                "student_id": student,
                "date": self.today.isoformat(),
            }
            self.history.append(history_entry)

            if self.db:
                self.db.save_transaction(transaction)
                if item:
                    self.db.update_item_status(item.item_id, item.status)
                if request:
                    self.db.update_request_status(request.request_id, request.status)
                self.db.save_cancellation(cancellation)
                self.db.save_history(history_entry)

            return True, "Accepted booking cancelled. Item is available again."

        return False, "Request or booking not found for this student."

    # ========================================================
    # SECTION 10: FINANCIAL CALCULATIONS & EARNINGS
    # ========================================================

    def calculate_totals(self, transaction: Transaction) -> dict:
        """
        Calculate total financial breakdown for a transaction:
        Total Due = rental_amount + late_fee + damage_charge.
        """
        total_due = round_money(
            transaction.rental_amount + transaction.late_fee + transaction.damage_charge
        )
        return {
            "rental_amount": transaction.rental_amount,
            "commission": transaction.commission,
            "lender_earnings": transaction.lender_earnings,
            "late_fee": transaction.late_fee,
            "damage_charge": transaction.damage_charge,
            "total_due": total_due,
        }

    def get_earnings(self, lender_id: str) -> dict:
        """
        Calculate total earnings for a lender from COMPLETED loans.
        App takes 10% commission; lender keeps 90%.
        """
        ok, lender = self.verify_student_id(lender_id)
        if not ok:
            return {
                "completed_transactions": 0,
                "rental_amount": 0.0,
                "commission": 0.0,
                "lender_earnings": 0.0,
            }

        # Find all completed transactions for this lender
        completed = [
            transaction
            for transaction in self.transactions.values()
            if transaction.lender_id == lender and transaction.status == "COMPLETED"
        ]
        rental = round_money(sum(transaction.rental_amount for transaction in completed))
        commission = round_money(sum(transaction.commission for transaction in completed))
        earnings = round_money(sum(transaction.lender_earnings for transaction in completed))
        return {
            "completed_transactions": len(completed),
            "rental_amount": rental,
            "commission": commission,
            "lender_earnings": earnings,
        }

    def get_borrowing_history(self, student_id: str) -> List[Transaction]:
        """
        Return all transactions where this student participated,
        either as the borrower or as the lender.
        """
        return [
            transaction
            for transaction in self.transactions.values()
            if transaction.borrower_id == student_id or transaction.lender_id == student_id
        ]

    # ========================================================
    # SECTION 11: ADMIN AUDIT LEDGER & REPORTS
    # ========================================================

    def get_master_ledger(self) -> List[dict]:
        """
        Master audit ledger:
        Returns a complete list of every item on campus showing:
        - Item details (ID, name, condition, daily price, status)
        - Lender details (ID, name)
        - Borrower details (ID, name, loan dates)
        - Return status: [NOT RETURNED], [LATE], [PENDING REQUEST], [RETURNED], or [AVAILABLE]
        """
        ledger: List[dict] = []

        for item_id, item in sorted(self.items.items()):
            lender = self.students.get(item.lender_id)
            lender_name = lender.name if lender else "Unknown"

            # Check transactions for this item
            item_txs = [t for t in self.transactions.values() if t.item_id == item_id]
            active_tx = next((t for t in item_txs if t.status == "BORROWED"), None)
            completed_txs = [t for t in item_txs if t.status == "COMPLETED"]

            # Check active pending request
            pending_req = next(
                (r for r in self.requests.values() if r.item_id == item_id and r.status == "PENDING"),
                None,
            )

            # 1. If currently borrowed and NOT returned
            if active_tx:
                borrower = self.students.get(active_tx.borrower_id)
                borrower_name = borrower.name if borrower else "Unknown"
                is_late = self.today > active_tx.due_date
                late_days = (self.today - active_tx.due_date).days if is_late else 0

                ret_details = f"[NOT RETURNED] (Due: {active_tx.due_date})"
                if late_days > 0:
                    ret_details += f" [LATE: {late_days}d]"

                ledger.append({
                    "item_id": item_id,
                    "item_name": item.name,
                    "item_condition": item.condition,
                    "daily_price": item.rental_price_per_day,
                    "item_status": item.status,
                    "lender_id": item.lender_id,
                    "lender_name": lender_name,
                    "borrower_id": active_tx.borrower_id,
                    "borrower_name": borrower_name,
                    "transaction_id": active_tx.transaction_id,
                    "start_date": active_tx.start_date,
                    "due_date": active_tx.due_date,
                    "rental_amount": active_tx.rental_amount,
                    "is_returned": False,
                    "return_status": "NOT RETURNED",
                    "return_details": ret_details,
                    "return_date": None,
                    "late_days": late_days,
                    "late_fee": 0.0,
                    "damage_charge": 0.0,
                    "total_charge": active_tx.rental_amount,
                })

            # 2. If pending borrow request
            elif pending_req:
                borrower = self.students.get(pending_req.borrower_id)
                borrower_name = borrower.name if borrower else "Unknown"
                est_rent = round_money(item.rental_price_per_day * pending_req.duration_days)

                ledger.append({
                    "item_id": item_id,
                    "item_name": item.name,
                    "item_condition": item.condition,
                    "daily_price": item.rental_price_per_day,
                    "item_status": item.status,
                    "lender_id": item.lender_id,
                    "lender_name": lender_name,
                    "borrower_id": pending_req.borrower_id,
                    "borrower_name": borrower_name,
                    "transaction_id": None,
                    "start_date": self.today,
                    "due_date": None,
                    "rental_amount": est_rent,
                    "is_returned": False,
                    "return_status": "PENDING REQUEST",
                    "return_details": f"[PENDING REQUEST] ({pending_req.duration_days} days)",
                    "return_date": None,
                    "late_days": 0,
                    "late_fee": 0.0,
                    "damage_charge": 0.0,
                    "total_charge": est_rent,
                })

            # 3. If item is available with past completed transactions
            elif completed_txs:
                latest_tx = sorted(completed_txs, key=lambda t: t.transaction_id, reverse=True)[0]
                borrower = self.students.get(latest_tx.borrower_id)
                borrower_name = borrower.name if borrower else "Unknown"
                ret_rec = next((r for r in self.returns.values() if r.transaction_id == latest_tx.transaction_id), None)
                ret_date = ret_rec.return_date if ret_rec else "Returned"
                ret_cond = ret_rec.return_condition if ret_rec else "Good"
                late_fee = ret_rec.late_fee if ret_rec else latest_tx.late_fee
                damage = ret_rec.damage_charge if ret_rec else latest_tx.damage_charge
                total = round_money(latest_tx.rental_amount + late_fee + damage)

                ledger.append({
                    "item_id": item_id,
                    "item_name": item.name,
                    "item_condition": item.condition,
                    "daily_price": item.rental_price_per_day,
                    "item_status": item.status,
                    "lender_id": item.lender_id,
                    "lender_name": lender_name,
                    "borrower_id": latest_tx.borrower_id,
                    "borrower_name": borrower_name,
                    "transaction_id": latest_tx.transaction_id,
                    "start_date": latest_tx.start_date,
                    "due_date": latest_tx.due_date,
                    "rental_amount": latest_tx.rental_amount,
                    "is_returned": True,
                    "return_status": "RETURNED",
                    "return_details": f"[RETURNED] on {ret_date} ({ret_cond})",
                    "return_date": ret_date,
                    "late_days": ret_rec.late_days if ret_rec else 0,
                    "late_fee": late_fee,
                    "damage_charge": damage,
                    "total_charge": total,
                })

            # 4. Item is available and was never borrowed
            else:
                ledger.append({
                    "item_id": item_id,
                    "item_name": item.name,
                    "item_condition": item.condition,
                    "daily_price": item.rental_price_per_day,
                    "item_status": item.status,
                    "lender_id": item.lender_id,
                    "lender_name": lender_name,
                    "borrower_id": "None",
                    "borrower_name": "None",
                    "transaction_id": None,
                    "start_date": None,
                    "due_date": None,
                    "rental_amount": 0.0,
                    "is_returned": None,
                    "return_status": "AVAILABLE",
                    "return_details": "[AVAILABLE] In Inventory",
                    "return_date": None,
                    "late_days": 0,
                    "late_fee": 0.0,
                    "damage_charge": 0.0,
                    "total_charge": 0.0,
                })

        return ledger

    def get_all_transactions_ledger(self) -> List[dict]:
        """
        Returns full historical list of all transactions with lender,
        borrower, item, and return status details.
        """
        records: List[dict] = []
        for tx_id, tx in sorted(self.transactions.items()):
            item = self.items.get(tx.item_id)
            item_name = item.name if item else "Unknown Item"
            lender = self.students.get(tx.lender_id)
            borrower = self.students.get(tx.borrower_id)
            ret_rec = next((r for r in self.returns.values() if r.transaction_id == tx_id), None)

            is_returned = tx.status == "COMPLETED"
            if is_returned:
                status_str = f"[RETURNED] on {ret_rec.return_date if ret_rec else 'Settled'}"
            elif tx.status == "CANCELLED":
                status_str = "[CANCELLED]"
            else:
                is_late = self.today > tx.due_date
                late_days = (self.today - tx.due_date).days if is_late else 0
                status_str = f"[NOT RETURNED] (Due: {tx.due_date})"
                if late_days > 0:
                    status_str += f" [LATE: {late_days}d]"

            records.append({
                "transaction_id": tx_id,
                "item_id": tx.item_id,
                "item_name": item_name,
                "lender_id": tx.lender_id,
                "lender_name": lender.name if lender else "Unknown",
                "borrower_id": tx.borrower_id,
                "borrower_name": borrower.name if borrower else "Unknown",
                "start_date": tx.start_date,
                "due_date": tx.due_date,
                "rental_amount": tx.rental_amount,
                "commission": tx.commission,
                "lender_earnings": tx.lender_earnings,
                "late_fee": tx.late_fee,
                "damage_charge": tx.damage_charge,
                "is_returned": is_returned,
                "status_details": status_str,
            })
        return records

    # --------------------------------------------------------
    # RELATIONAL AUDIT & REPORT METHODS
    # --------------------------------------------------------
    def get_lender_inventory_report(self, lender_filter: Optional[str] = None) -> List[dict]:
        """
        Returns structured lender inventory records where:
        - 1st: lender_id
        - 2nd: lender_name
        - item_id, item_name, cost_per_day, item_condition, item_status
        """
        if self.db:
            return self.db.get_lender_inventory_report(lender_filter)

        results: List[dict] = []
        for item_id, item in sorted(self.items.items()):
            if lender_filter and item.lender_id != lender_filter:
                continue
            student = self.students.get(item.lender_id)
            item_status = item.status
            for tx in self.transactions.values():
                if tx.item_id == item.item_id and tx.status == "RETURN_PENDING":
                    item_status = "RETURN_PENDING"
                    break

            results.append({
                "lender_id": item.lender_id,
                "lender_name": student.name if student else "Unknown",
                "item_id": item.item_id,
                "item_name": item.name,
                "cost_per_day": item.rental_price_per_day,
                "item_condition": item.condition,
                "item_status": item_status,
            })
        return sorted(results, key=lambda x: (x["lender_id"], x["item_id"]))

    def get_borrower_loans_report(self, lender_filter: Optional[str] = None) -> List[dict]:
        """
        Returns multi-table relational view of loans showing who borrowed what
        from a particular lender AU_ID and for how many days.
        """
        if self.db:
            return self.db.get_borrower_loans_report(lender_filter)

        results: List[dict] = []
        for tx_id, tx in sorted(self.transactions.items()):
            if lender_filter and tx.lender_id != lender_filter:
                continue
            borrower = self.students.get(tx.borrower_id)
            lender = self.students.get(tx.lender_id)
            item = self.items.get(tx.item_id)
            results.append({
                "transaction_id": tx.transaction_id,
                "request_id": tx.request_id,
                "borrower_id": tx.borrower_id,
                "borrower_name": borrower.name if borrower else "Unknown",
                "lender_id": tx.lender_id,
                "lender_name": lender.name if lender else "Unknown",
                "item_id": tx.item_id,
                "item_name": item.name if item else "Unknown",
                "daily_rent": tx.daily_rent,
                "duration_days": tx.duration_days,
                "rental_amount": tx.rental_amount,
                "commission": tx.commission,
                "lender_earnings": tx.lender_earnings,
                "start_date": tx.start_date.isoformat() if hasattr(tx.start_date, "isoformat") else str(tx.start_date),
                "due_date": tx.due_date.isoformat() if hasattr(tx.due_date, "isoformat") else str(tx.due_date),
                "returned_on": tx.returned_on.isoformat() if tx.returned_on and hasattr(tx.returned_on, "isoformat") else (str(tx.returned_on) if tx.returned_on else None),
                "transaction_status": tx.status,
                "late_days": tx.late_days,
                "late_fee": tx.late_fee,
                "damage_charge": tx.damage_charge,
                "return_condition": tx.return_condition,
            })
        return sorted(results, key=lambda x: (x["lender_id"], x["transaction_id"]))

    def get_pending_borrower_requests_report(self, lender_filter: Optional[str] = None) -> List[dict]:
        """
        Returns pending requests showing borrowers requesting items from a particular lender AU_ID.
        """
        if self.db:
            return self.db.get_pending_borrower_requests_report(lender_filter)

        results: List[dict] = []
        for req_id, req in sorted(self.requests.items()):
            if req.status != "PENDING":
                continue
            if lender_filter and req.lender_id != lender_filter:
                continue
            borrower = self.students.get(req.borrower_id)
            lender = self.students.get(req.lender_id)
            item = self.items.get(req.item_id)
            results.append({
                "request_id": req.request_id,
                "borrower_id": req.borrower_id,
                "borrower_name": borrower.name if borrower else "Unknown",
                "lender_id": req.lender_id,
                "lender_name": lender.name if lender else "Unknown",
                "item_id": req.item_id,
                "item_name": item.name if item else "Unknown",
                "cost_per_day": item.rental_price_per_day if item else 0.0,
                "duration_days": req.duration_days,
                "requested_on": req.requested_on.isoformat() if hasattr(req.requested_on, "isoformat") else str(req.requested_on),
                "request_status": req.status,
            })
        return sorted(results, key=lambda x: (x["lender_id"], x["request_id"]))

    def get_dbms_diagnostics(self) -> dict:
        """
        Returns database telemetry and statistics.
        """
        if self.db:
            return self.db.get_dbms_diagnostics()
        return {
            "counts": {
                "students": len(self.students),
                "items": len(self.items),
                "borrow_requests": len(self.requests),
                "transactions": len(self.transactions),
                "return_records": len(self.returns),
                "cancellations": len(self.cancellations),
                "audit_history": len(self.history),
            },
            "integrity": "ok (in-memory mode)",
            "fk_violations": 0,
            "db_path": ":memory:",
        }

    def get_active_students_summary(self) -> dict:
        """
        Calculates truthful active user metrics:
        - registered: students who logged in and set their PIN
        - total_active: distinct students active in the system
        """
        if self.db:
            return self.db.get_active_students_summary()
        registered = len([s for s in self.students.values() if s.pin])
        active = set(s.student_id for s in self.students.values() if s.pin)
        for i in self.items.values():
            active.add(i.lender_id)
        for t in self.transactions.values():
            active.add(t.borrower_id)
            active.add(t.lender_id)
        return {"registered": registered, "total_active": len(active)}

    # --------------------------------------------------------
    # CLOUD SYNCHRONIZATION INTERFACE
    # --------------------------------------------------------
    def get_cloud_status(self) -> dict:
        if self.db:
            return self.db.get_cloud_status()
        return {"configured": False, "status": "Disabled (in-memory mode)"}

    def sync_push_to_cloud(self) -> Tuple[bool, str, dict]:
        if self.db:
            return self.db.sync_push_to_cloud()
        return False, "Database not attached.", {}

    def prune_cloud_students(self) -> Tuple[bool, str, int]:
        if self.db:
            return self.db.prune_cloud_students()
        return False, "Database not attached.", 0

    def configure_cloud(self, url: str, key: str) -> Tuple[bool, str]:
        if self.db:
            return self.db.configure_cloud(url, key)
        return False, "Database not attached."

    def test_cloud_connection(self) -> Tuple[bool, str]:
        if self.db:
            return self.db.test_cloud_connection()
        return False, "Database not attached."



