# =============================================================================
# main.py  —  USER INTERFACE (CLI) FOR "BORROW INSTEAD OF BUY" APP
# =============================================================================
# What this file does:
#   1. Runs the interactive command-line interface with colorful menus.
#   2. Handles student login, 4-digit PIN verification, and real-time dot password masking.
#   3. Provides menus for Lenders (add items, view requests, see earnings),
#      Borrowers (search items, request borrow, return with damage calculation),
#      and Administrators (master ledger dashboard, DBMS diagnostics, cloud sync).
#
# HOW IT CONNECTS TO OTHER FILES:
#   - logic.py         : contains all the business rules, formulas, and data models
#   - database.py      : handles the SQLite database (borrow_app.db)
#   - supabase_sync.py : handles online cloud sync (Supabase)
# =============================================================================

import os
import sys
from typing import Tuple

# Load environment variables (like SUPABASE_KEY) from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except Exception:
    pass

# Enable native ANSI color escape sequences on Windows command prompt / PowerShell
if os.name == "nt":
    os.system("")

# Configure UTF-8 encoding so emojis and rupee symbols (₹) display cleanly
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Import core business classes and calculation functions from logic.py
from logic import (
    BorrowInsteadOfBuyApp,
    Item,
    parse_positive_float,
    parse_positive_int,
    calculate_damage_charge,
)


# =============================================================================
# COLOR DEFINITIONS (ANSI Escape Codes)
# These codes tell the terminal to print text in different colors and styles.
# Example: print(f"{C.GREEN}Hello{C.RESET}") prints "Hello" in green!
# =============================================================================
class C:
    RESET     = "\033[0m"     # Resets back to default terminal color
    BOLD      = "\033[1m"     # Bold / bright text
    DIM       = "\033[2m"     # Dim / faint text
    UNDERLINE = "\033[4m"     # Underlined text

    RED       = "\033[91m"    # Red (for errors, alerts, severe damage)
    GREEN     = "\033[92m"    # Green (for success, active, completed)
    YELLOW    = "\033[93m"    # Yellow (for warnings, pending items)
    BLUE      = "\033[94m"    # Blue
    MAGENTA   = "\033[95m"    # Magenta / Purple
    CYAN      = "\033[96m"    # Cyan (for titles, headers, highlights)
    WHITE     = "\033[97m"    # Bright White
    GRAY      = "\033[90m"    # Muted Gray (for secondary details)

    BG_CYAN   = "\033[46;30m" # Cyan background with black text
    BG_GREEN  = "\033[42;30m" # Green background with black text
    BG_RED    = "\033[41;97m" # Red background with white text
    BG_YELLOW = "\033[43;30m" # Yellow background with black text


# =============================================================================
# HELPER FUNCTIONS FOR DISPLAY & FORMATTING
# =============================================================================

def pad_c(text: object, width: int, color: str = "", align: str = "<") -> str:
    """
    Format text to a fixed width with optional color and alignment.
    Keeps table columns perfectly aligned on screen.
    """
    t = str(text)
    if len(t) > width:
        t = t[:width - 2] + ".."  # Truncate with .. if too long
    padded = f"{t:{align}{width}}"
    return f"{color}{padded}{C.RESET}" if color else padded


def money(value: float) -> str:
    """
    Format a number as Indian Rupees: e.g. 150.0 -> '₹150', 50.5 -> '₹50.50'
    """
    value = round(float(value) + 1e-10, 2)
    return f"₹{value:,.2f}".rstrip("0").rstrip(".")


# =============================================================================
# MAIN CLI CLASS: BorrowInsteadOfBuyCLI
# Handles user interaction, menus, inputs, and screens.
# =============================================================================
class BorrowInsteadOfBuyCLI:
    def __init__(self, app: BorrowInsteadOfBuyApp | None = None):
        # Connect to the backend application (loads borrow_app.db)
        self.app = app or BorrowInsteadOfBuyApp(db_path="borrow_app.db")

    @staticmethod
    def header(title: str) -> None:
        print("\n" + f"{C.CYAN}{C.BOLD}" + "=" * 68 + f"{C.RESET}")
        print(f"{C.CYAN}{C.BOLD}{title:^68}{C.RESET}")
        print(f"{C.CYAN}{C.BOLD}" + "=" * 68 + f"{C.RESET}")

    @staticmethod
    def pause() -> None:
        input("\nPress Enter to continue...")

    @staticmethod
    def ask(prompt: str) -> str:
        return input(prompt).strip()

    @staticmethod
    def ask_password(prompt: str = "Enter Password: ", mask_char: str = "●") -> str:
        """
        Secure password/PIN input with direct dot conversion:
        Every character entered is immediately printed as a dot ('●') in real-time,
        ensuring actual password characters are NEVER visible on screen.
        Supports Backspace (erases dot), Enter (submits), and Ctrl+C (cancels).
        """
        print(prompt, end="", flush=True)

        if not sys.stdin.isatty() or os.name != "nt":
            import getpass
            try:
                return getpass.getpass("").strip()
            except Exception:
                return input().strip()

        import msvcrt

        chars = []

        while True:
            ch = msvcrt.getch()

            # Enter
            if ch in (b'\r', b'\n'):
                print()
                break

            # Backspace
            elif ch == b'\x08':
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()

            # Ctrl+C
            elif ch == b'\x03':
                print()
                raise KeyboardInterrupt

            # Ignore arrow keys and function keys
            elif ch in (b'\x00', b'\xe0'):
                msvcrt.getch()

            else:
                try:
                    char_str = ch.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        char_str = ch.decode("cp1252")
                    except Exception:
                        continue

                if char_str.isprintable():
                    chars.append(char_str)
                    try:
                        sys.stdout.write(mask_char)
                    except Exception:
                        sys.stdout.write("*")
                    sys.stdout.flush()

        return "".join(chars).strip()

    @staticmethod
    def parse_menu_index(raw: str, maximum: int) -> int:
        try:
            number = int(raw)
        except ValueError:
            return -1
        if number == 0:
            return 0
        if 1 <= number <= maximum:
            return number
        return -1

    # --------------------------------------------------------
    # STUDENT VERIFICATION
    # --------------------------------------------------------
    def verify_role(self, role: str) -> str | None:
        self.header(f"{role.upper()} - STUDENT VERIFICATION")
        print("Enter Student ID (AU25UG001 - AU25UG100) or Roll Number (1 - 100)")
        print("Type B to go back.\n")

        while True:
            raw = self.ask("Enter Student ID or Roll No: ")
            if raw.upper() == "B":
                return None

            ok, student_id = self.app.normalize_student_input(raw)
            if not ok:
                print(f"\n✗ {student_id}")
                print("Please try again.\n")
                continue

            student_name = self.app.students[student_id].name
            existing_pin = self.app.get_student_pin(student_id)

            # First-time setup: student has not set a PIN yet
            if not existing_pin:
                print(f"\n👋 Welcome, {student_name} ({student_id})!")
                print("🔒 [FIRST-TIME SETUP] Create your personal 4-digit Security PIN.")
                while True:
                    new_pin = self.ask_password("Enter 4-digit PIN (e.g. 1234): ")
                    if new_pin.upper() == "B":
                        return None
                    pin_ok, pin_msg = self.app.set_student_pin(student_id, new_pin)
                    if pin_ok:
                        print(f"✓ Security PIN created successfully!")
                        print(f"✓ Access Granted: {student_id} ({student_name})")
                        self.pause()
                        return student_id
                    print(f"✗ {pin_msg}")

            # Returning login: verify existing PIN
            print(f"\nAccount: {student_id} ({student_name})")
            attempts = 3
            while attempts > 0:
                entered_pin = self.ask_password("Enter 4-digit PIN: ")
                if entered_pin.upper() == "B":
                    return None
                if self.app.verify_student_pin(student_id, entered_pin):
                    print(f"\n✓ Verified! Access Granted: {student_id} ({student_name})")
                    self.pause()
                    return student_id
                attempts -= 1
                if attempts > 0:
                    print(f"✗ Incorrect PIN. {attempts} attempt(s) remaining.")
                else:
                    print("✗ Incorrect PIN. Access denied.")
                    self.pause()
                    return None

    # --------------------------------------------------------
    # LENDER MENU
    # --------------------------------------------------------
    def lender_menu(self, lender_id: str) -> None:
        while True:
            self.header(f"LENDER MENU | {lender_id}")

            pending_requests = [
                req for req in self.app.requests.values()
                if req.lender_id == lender_id and req.status == "PENDING"
            ]
            pending_returns = [
                ret for ret in self.app.returns.values()
                if ret.lender_id == lender_id and ret.status == "RETURN_SUBMITTED"
                and ret.return_condition != "COMPLETE DAMAGE"
            ]

            if pending_requests or pending_returns:
                print(f"🔔 NOTIFICATIONS: {len(pending_requests)} request(s) waiting | {len(pending_returns)} return(s) waiting")
                print("0. ⚡ 1-Click Approve & Settle All Pending")

            print("1. Add Item for Lending")
            print("2. View My Listed Items")
            print("3. View Earnings & Commission")
            print("4. View Borrowing / Lending History")
            print("5. Back")
            choice = self.ask("\nEnter choice: ")

            if choice == "0" and (pending_requests or pending_returns):
                self.ui_quick_approve_all(lender_id, pending_requests, pending_returns)
            elif choice == "1":
                self.ui_add_item(lender_id)
            elif choice == "2":
                self.ui_view_lender_items(lender_id)
            elif choice == "3":
                self.ui_earnings(lender_id)
            elif choice == "4":
                self.ui_history(lender_id)
            elif choice == "5":
                return
            else:
                print("\n✗ Invalid menu choice.")

    def ui_quick_approve_all(self, lender_id: str, requests: list, returns: list) -> None:
        self.header("QUICK APPROVE & SETTLE")
        count_req = 0
        for req in requests:
            ok, tx_id = self.app.accept_request(lender_id, req.request_id)
            if ok:
                count_req += 1
                print(f"✓ Accepted Request {req.request_id} -> Created Transaction {tx_id}")

        count_ret = 0
        for ret in returns:
            ok, msg = self.app.confirm_return(lender_id, ret.return_id)
            if ok:
                count_ret += 1
                print(f"✓ Confirmed Return {ret.return_id} -> Item released to Available")

        print(f"\n⚡ Done! {count_req} request(s) approved, {count_ret} return(s) settled.")
        self.pause()

    @staticmethod
    def validate_item_name(raw_name: str) -> Tuple[bool, str]:
        name = raw_name.strip()
        if not name:
            return False, "Item name cannot be empty."
        if len(name) < 3:
            return False, "Item name must be at least 3 characters long."
        if name.isdigit():
            return False, "Item name cannot be purely numbers (e.g. '1234'). Please enter a real item name."
        
        common_mash = {"asdf", "asdfg", "asdfgh", "qwerty", "zxcv", "zxcvb", "test", "xxx", "aaa", "bbb", "1234"}
        if name.lower() in common_mash:
            return False, "Item name appears to be keyboard mash. Please enter a valid campus item (e.g. 'Casio Calculator', 'Drawing Drafter')."

        letters = sum(1 for c in name if c.isalpha())
        if letters < 2:
            return False, "Item name must contain at least 2 letters (e.g. 'Lab Coat', 'Camera')."

        if not any(c.isalnum() for c in name):
            return False, "Item name cannot consist only of symbols."

        for raw_w in name.split():
            w = raw_w.strip(",.;:()[]{}")
            if len(w) >= 6 and w[:3].isdigit() and any(c.isalpha() for c in w[3:]):
                return False, f"'{raw_w}' looks like random mixed characters. Please provide a clear, recognized item name."
            if len(w) >= 5 and w.isalpha() and not any(v in w.lower() for v in "aeiouy"):
                return False, f"'{raw_w}' contains no vowels and looks like random keyboard typing."

        return True, name

    def ui_pick_condition(self) -> str | None:
        """
        Interactive 5-star condition picker:
        Displays 5 stars. Pressing 1-5 or Left/Right arrows instantly illuminates
        the stars in glowing gold. Press Enter to confirm.
        """
        print(f"\n{C.BOLD}Item Condition Rating (5 Stars):{C.RESET}")
        print(f"{C.GRAY}  [1] ★☆☆☆☆ Poor       (Heavy wear, fully functional)")
        print(f"  [2] ★★☆☆☆ Fair       (Visible cosmetic wear, acceptable)")
        print(f"  [3] ★★★☆☆ Good       (Normal campus wear & tear)")
        print(f"  [4] ★★★★☆ Very Good  (Minor signs of use, clean)")
        print(f"  [5] ★★★★★ Pristine   (Brand new / Flawless){C.RESET}\n")

        labels = {
            1: "★☆☆☆☆ Poor",
            2: "★★☆☆☆ Fair",
            3: "★★★☆☆ Good",
            4: "★★★★☆ Very Good",
            5: "★★★★★ Pristine",
        }
        descriptions = {
            1: "Poor - Heavily used",
            2: "Fair - Visible wear",
            3: "Good - Normal condition",
            4: "Very Good - Minor wear",
            5: "Pristine - Brand new",
        }

        rating = 4  # Default to 4 (Very Good)
        use_interactive = sys.stdin.isatty() and os.name == "nt"

        if use_interactive:
            try:
                import msvcrt
                print(f"  {C.CYAN}👉 Press [1-5] (or ←/→ arrows) to light up stars. Press [Enter] to select:{C.RESET}")
                while True:
                    filled = "★ " * rating
                    empty = "☆ " * (5 - rating)
                    stars_glow = f"{C.YELLOW}{C.BOLD}{filled}{C.RESET}{C.GRAY}{empty}{C.RESET}"
                    label_text = f"{C.WHITE}{C.BOLD}{labels[rating]}{C.RESET}"
                    desc_text = f"{C.CYAN}({descriptions[rating]}){C.RESET}"
                    
                    sys.stdout.write(f"\r  ⭐ Condition: {stars_glow}  {label_text}  {desc_text}   ")
                    sys.stdout.flush()

                    ch = msvcrt.getch()
                    if ch in (b'\r', b'\n'):  # Enter to confirm
                        print("\n")
                        print(f"  {C.GREEN}✓ Selected Condition:{C.RESET} {C.YELLOW}{C.BOLD}{'★ ' * rating}{C.RESET}{C.GRAY}{'☆ ' * (5 - rating)}{C.RESET} {labels[rating]}\n")
                        return labels[rating]
                    elif ch in (b'b', b'B', b'\x1b'):  # Back / Cancel
                        print("\n")
                        return None
                    elif ch in (b'1', b'2', b'3', b'4', b'5'):
                        rating = int(ch.decode("ascii"))
                    elif ch in (b'\x00', b'\xe0'):  # Arrow keys
                        arrow = msvcrt.getch()
                        if arrow in (b'K', b'P'):  # Left / Down
                            rating = max(1, rating - 1)
                        elif arrow in (b'M', b'H'):  # Right / Up
                            rating = min(5, rating + 1)
            except Exception:
                pass

        # Fallback for piped or non-interactive terminal
        while True:
            choice = self.ask("Select Condition Rating [1-5, default: 4, B to cancel]: ").strip()
            if choice.upper() == "B":
                return None
            if not choice:
                return labels[4]
            if choice in ("1", "2", "3", "4", "5"):
                r = int(choice)
                print(f"\n  {C.GREEN}✓ Selected Condition:{C.RESET} {labels[r]}\n")
                return labels[r]
            print("✗ Enter a number between 1 and 5.")

    def ui_add_item(self, lender_id: str) -> None:
        self.header("ADD ITEM FOR LENDING")

        while True:
            raw_name = self.ask("Item name: ").strip()
            if raw_name.upper() == "B":
                return
            ok_name, name_val = self.validate_item_name(raw_name)
            if ok_name:
                name = name_val
                break
            print(f"✗ {name_val}\n")

        condition = self.ui_pick_condition()
        if not condition:
            return

        while True:
            raw_price = self.ask("Rental price per day (₹): ").strip()
            if raw_price.upper() == "B":
                return
            price = parse_positive_float(raw_price)
            if price is not None:
                break
            print("✗ Enter a positive numeric rental price.")

        ok, result = self.app.add_item(lender_id, name, condition, price)
        if ok:
            print(f"\n{C.GREEN}✓ Item listed successfully!{C.RESET}")
            print(f"  {C.BOLD}Generated Item ID :{C.RESET} {result}")
            print(f"  {C.BOLD}Item Name         :{C.RESET} {name}")
            print(f"  {C.BOLD}Condition Rating  :{C.RESET} {condition}")
            print(f"  {C.BOLD}Daily Rental Price:{C.RESET} {money(price)}/day")
        else:
            print(f"\n✗ {result}")
        self.pause()

    def ui_view_lender_items(self, lender_id: str) -> None:
        while True:
            self.header("MY LISTED ITEMS")
            items = self.app.get_lender_items(lender_id)
            if not items:
                print("No items listed.")
                self.pause()
                return

            for index, item in enumerate(items, 1):
                print(
                    f"{index}. {item.item_id:<6} | {item.name:<22} | "
                    f"{item.condition:<16} | {money(item.rental_price_per_day)}/day | {item.status}"
                )

                pending_request = next(
                    (
                        request for request in self.app.requests.values()
                        if request.item_id == item.item_id and request.status == "PENDING"
                    ),
                    None,
                )
                pending_return = self.app.get_pending_return_for_item(item.item_id)

                if pending_request:
                    print(
                        f"   ↳ PENDING BORROW REQUEST: {pending_request.borrower_id}, "
                        f"{pending_request.duration_days} day(s)"
                    )
                if pending_return:
                    transaction = self.app.transactions[pending_return.transaction_id]
                    print(
                        f"   ↳ RETURN WAITING: {pending_return.borrower_id}, "
                        f"Condition: {pending_return.return_condition}"
                    )
                    print(f"      Return date: {pending_return.return_date.isoformat()}")
                    print(f"      Late days : {pending_return.late_days}")
                    print(f"      Late fee  : {money(pending_return.late_fee)}")
                    print(f"      Damage    : {money(pending_return.damage_charge)}")
                    if pending_return.return_condition == "COMPLETE DAMAGE":
                        print(f"      Consult the {transaction.lender_id} lender for further consequences.")
                        print("      Pay the full amount of the item to the lender.")
                        print(f"      {C.CYAN}👉 Select item [{index}] below to settle compensation & close issue.{C.RESET}")

            print("\nSelect an item number to manage it. Enter 0 to back.")
            index = self.parse_menu_index(self.ask("Choice: "), len(items))
            if index == 0:
                return
            if index == -1:
                print("\n✗ Invalid selection.")
                continue

            self.ui_manage_lender_item(lender_id, items[index - 1])

    def ui_manage_lender_item(self, lender_id: str, item: Item) -> None:
        while True:
            self.header(f"ITEM | {item.item_id} - {item.name}")
            print(f"Condition : {item.condition}")
            print(f"Rent/day  : {money(item.rental_price_per_day)}")
            print(f"Status    : {item.status}")

            pending_request = next(
                (
                    request for request in self.app.requests.values()
                    if request.item_id == item.item_id and request.status == "PENDING"
                ),
                None,
            )
            pending_return = self.app.get_pending_return_for_item(item.item_id)

            if pending_request:
                print("\n--- BORROW REQUEST ---")
                print(f"Borrower : {pending_request.borrower_id}")
                print(f"Duration : {pending_request.duration_days} day(s)")
                print(f"Rent     : {money(item.rental_price_per_day * pending_request.duration_days)}")
                print("\n1. Accept Request")
                print("2. Reject Request")
                print("3. Back")
                choice = self.ask("Choice: ")
                if choice == "1":
                    ok, result = self.app.accept_request(lender_id, pending_request.request_id)
                    message = result if not ok else f"Request accepted. Transaction {result} created."
                    print(f"\n{'✓' if ok else '✗'} {message}")
                    self.pause()
                    return
                if choice == "2":
                    ok, result = self.app.reject_request(lender_id, pending_request.request_id)
                    print(f"\n{'✓' if ok else '✗'} {result}")
                    self.pause()
                    return
                if choice == "3":
                    return
                print("\n✗ Invalid choice.")
                continue

            if pending_return:
                transaction = self.app.transactions[pending_return.transaction_id]
                print("\n--- RETURN DETAILS FROM BORROWER ---")
                print(f"Borrower    : {pending_return.borrower_id}")
                print(f"Return date : {pending_return.return_date.isoformat()}")
                print(f"Condition   : {pending_return.return_condition}")
                print(f"Late days   : {pending_return.late_days}")
                print(f"Late fee    : {money(pending_return.late_fee)}")
                print(f"Damage      : {money(pending_return.damage_charge)}")

                if pending_return.return_condition == "COMPLETE DAMAGE":
                    print(f"\n{C.YELLOW}⚠️  Note:{C.RESET} Complete damage compensation is handled directly with the borrower.")
                    print("Pay the full amount of the item to the lender.")
                    print(f"\nOnce {pending_return.borrower_id} has paid the full replacement compensation to you:")
                    print("1. Confirm Full Payment Received & Close Issue")
                    print("2. Back")
                    choice = self.ask("Choice: ")
                    if choice == "1":
                        ok, result = self.app.settle_complete_damage(lender_id, pending_return.return_id)
                        print(f"\n{'✓' if ok else '✗'} {result}")
                        self.pause()
                        return
                    if choice == "2":
                        return
                    print("\n✗ Invalid choice.")
                    continue

                print("\n1. Confirm Return")
                print("2. Back")
                choice = self.ask("Choice: ")
                if choice == "1":
                    ok, result = self.app.confirm_return(lender_id, pending_return.return_id)
                    print(f"\n{'✓' if ok else '✗'} {result}")
                    self.pause()
                    return
                if choice == "2":
                    return
                print("\n✗ Invalid choice.")
                continue

            active = next(
                (
                    transaction for transaction in self.app.transactions.values()
                    if transaction.item_id == item.item_id
                    and transaction.lender_id == lender_id
                    and transaction.status == "BORROWED"
                ),
                None,
            )
            if active:
                print(f"\nBorrower   : {active.borrower_id}")
                print(f"Start date : {active.start_date.isoformat()}")
                print(f"Due date   : {active.due_date.isoformat()}")
                print(f"Rental     : {money(active.rental_amount)}")
                print("\n1. Back")
                if self.ask("Choice: ") == "1":
                    return
                print("\n✗ Invalid choice.")
                continue

            print("\nNo pending request or return activity for this item.")
            print("\n1. Back")
            if self.ask("Choice: ") == "1":
                return
            print("\n✗ Invalid choice.")

    def ui_earnings(self, lender_id: str) -> None:
        self.header("EARNINGS & COMMISSION")
        data = self.app.get_earnings(lender_id)
        print(f"Completed transactions : {data['completed_transactions']}")
        print(f"Rental amount          : {money(data['rental_amount'])}")
        print(f"Commission (10%)       : {money(data['commission'])}")
        print(f"Lender earnings (90%)  : {money(data['lender_earnings'])}")
        self.pause()

    # --------------------------------------------------------
    # BORROWER MENU
    # --------------------------------------------------------
    def borrower_menu(self, borrower_id: str) -> None:
        while True:
            self.header(f"BORROWER MENU | {borrower_id}")
            print("1. Find / Request an Item")
            print("2. Return an Item")
            print("3. View Charges / Payment Summary")
            print("4. Cancel Request / Booking")
            print("5. View Borrowing History")
            print("6. Back")
            choice = self.ask("\nEnter choice: ")

            if choice == "1":
                self.ui_browse_and_request(borrower_id)
            elif choice == "2":
                self.ui_return_item(borrower_id)
            elif choice == "3":
                self.ui_charges(borrower_id)
            elif choice == "4":
                self.ui_cancel(borrower_id)
            elif choice == "5":
                self.ui_history(borrower_id)
            elif choice == "6":
                return
            else:
                print("\n✗ Invalid menu choice. Choose 1 to 6.")

    def ui_browse_and_request(self, borrower_id: str) -> None:
        self.header("AVAILABLE ITEMS")
        items = self.app.search_items()
        if not items:
            print("No available items right now.")
            self.pause()
            return

        for index, item in enumerate(items, 1):
            print(
                f"{index}. {item.item_id} | {item.name} | {item.condition} | "
                f"{money(item.rental_price_per_day)}/day | Lender: {item.lender_id}"
            )

        print("\nSelect an item number. Enter 0 to back.")
        index = self.parse_menu_index(self.ask("Choice: "), len(items))
        if index == 0:
            return
        if index == -1:
            print("\n✗ Invalid selection.")
            self.pause()
            return

        selected = items[index - 1]
        while True:
            duration = parse_positive_int(self.ask("Borrowing duration (days): "))
            if duration is not None:
                break
            print("✗ Enter a positive whole number of days.")

        ok, result = self.app.create_borrow_request(borrower_id, selected.item_id, duration)
        if not ok:
            print(f"\n✗ {result}")
            self.pause()
            return

        request_id = result
        print(f"\n✓ Borrow request created: {request_id} (Item: {selected.name})")
        print("✓ Request is pending lender approval.")
        self.pause()

    def ui_return_item(self, borrower_id: str) -> None:
        self.header("RETURN AN ITEM")
        active = self.app.get_active_borrowings(borrower_id)
        if not active:
            print("No active borrowed items.")
            self.pause()
            return

        for index, transaction in enumerate(active, 1):
            item = self.app.items[transaction.item_id]
            print(
                f"{index}. {transaction.transaction_id} | {item.name} | "
                f"Due: {transaction.due_date.isoformat()}"
            )

        print("\nSelect a transaction number. Enter 0 to back.")
        index = self.parse_menu_index(self.ask("Choice: "), len(active))
        if index == 0:
            return
        if index == -1:
            print("\n✗ Invalid selection.")
            self.pause()
            return

        transaction = active[index - 1]
        item = self.app.items[transaction.item_id]

        # ── Condition menu with damage rate hints ─────────────────────────
        print(f"\n{C.BOLD}Return Condition{C.RESET}")
        print(f"  {C.GREEN}1. No Damage{C.RESET}       {C.DIM}(no extra charge){C.RESET}")
        print(f"  {C.YELLOW}2. Minor Damage{C.RESET}    {C.DIM}(+15% of rental){C.RESET}")
        print(f"  {C.YELLOW}3. Moderate Damage{C.RESET} {C.DIM}(+55% of rental){C.RESET}")
        print(f"  {C.RED}4. Severe Damage{C.RESET}   {C.DIM}(+90% of rental){C.RESET}")
        print(f"  {C.BG_RED}5. Complete Damage{C.RESET} {C.DIM}(full item cost — handled separately){C.RESET}")
        choice = self.ask("Choice: ")
        conditions = {
            "1": "NO DAMAGE",
            "2": "MINOR",
            "3": "MODERATE",
            "4": "SEVERE",
            "5": "COMPLETE DAMAGE",
        }
        condition = conditions.get(choice)
        if not condition:
            print("\n✗ Invalid return condition.")
            self.pause()
            return

        # ── Cost preview (only for damaged conditions) ────────────────────
        if condition not in ("NO DAMAGE", "COMPLETE DAMAGE"):
            dmg_charge = calculate_damage_charge(transaction.rental_amount, condition) or 0.0
            total_due   = round(transaction.rental_amount + dmg_charge, 2)
            rate_label  = {"MINOR": "15%", "MODERATE": "55%", "SEVERE": "90%"}.get(condition, "")
            cond_color  = C.YELLOW if condition == "MINOR" else (C.RED if condition == "SEVERE" else C.YELLOW)
            print()
            print(f"{cond_color}{C.BOLD}╔══ 💸 RETURN COST BREAKDOWN ══════════════════════════════╗{C.RESET}")
            print(f"{cond_color}║{C.RESET}  📦 Item           : {C.BOLD}{item.name}{C.RESET}")
            print(f"{cond_color}║{C.RESET}  🎒 Rental Amount  : {C.GREEN}{C.BOLD}{money(transaction.rental_amount)}{C.RESET}")
            print(f"{cond_color}║{C.RESET}  ⚠️  Damage Charge  : {cond_color}{C.BOLD}+{money(dmg_charge)}{C.RESET}  {C.DIM}({rate_label} of rental — {condition}){C.RESET}")
            print(f"{cond_color}║{C.RESET}  {C.BOLD}─────────────────────────────────────────────────────{C.RESET}")
            print(f"{cond_color}║{C.RESET}  💰 {C.BOLD}Total to Pay   : {C.WHITE}{C.BOLD}{money(total_due)}{C.RESET}  {C.DIM}(pay to lender: {transaction.lender_id}){C.RESET}")
            print(f"{cond_color}{C.BOLD}╚═══════════════════════════════════════════════════════════╝{C.RESET}")
            print()

        ok, result = self.app.return_item(borrower_id, transaction.transaction_id, condition)
        if condition == "COMPLETE DAMAGE" and ok:
            print(f"\n{C.BG_RED}{C.BOLD} ⚠ COMPLETE DAMAGE / LOSS {C.RESET}")
            print(f"  {result}")
            print("  The full replacement cost must be settled directly with the lender.")
            self.pause()
            return

        if not ok:
            print(f"\n✗ {result}")
            self.pause()
            return

        ret_id = result
        print(f"\n{C.GREEN}✓ Return record {ret_id} submitted.{C.RESET}")

        # Instant Return Settlement Shortcut
        print(f"\n{C.CYAN}⚡ [INSTANT SETTLEMENT]{C.RESET}")
        print("Would you like to auto-confirm this return now on behalf of the lender?")
        print("1. Yes - Instant Settle (Completes transaction & resets item to Available)")
        print("2. No  - Standard Flow (Leaves return pending for manual lender confirmation)")
        instant_settle = self.ask("Choice [default: 1]: ")
        if instant_settle in ("", "1", "y", "Y"):
            ok_conf, conf_msg = self.app.confirm_return(transaction.lender_id, ret_id)
            if ok_conf:
                print(f"\n{C.GREEN}✓ Return Confirmed & Completed!{C.RESET}")
                print(f"  Item '{C.BOLD}{item.name}{C.RESET}' is now AVAILABLE again.")
                print(f"  Transaction {transaction.transaction_id} is COMPLETED.")
            else:
                print(f"\n✗ Could not auto-confirm: {conf_msg}")
        else:
            print(f"\n{C.CYAN}✓ Return submitted. Waiting for lender confirmation.{C.RESET}")
        self.pause()


    def ui_charges(self, borrower_id: str) -> None:
        self.header("CHARGES / PAYMENT SUMMARY")
        transactions = [
            transaction
            for transaction in self.app.transactions.values()
            if transaction.borrower_id == borrower_id
        ]
        if not transactions:
            print("No charges or borrowing records.")
            self.pause()
            return

        for transaction in transactions:
            totals = self.app.calculate_totals(transaction)
            item = self.app.items[transaction.item_id]
            print(f"\nTransaction: {transaction.transaction_id} | Item: {item.name}")
            print(f"Rental amount : {money(totals['rental_amount'])}")
            print(f"Commission    : {money(totals['commission'])}")
            print(f"Lender earns  : {money(totals['lender_earnings'])}")
            print(f"Late fee      : {money(totals['late_fee'])}")
            print(f"Damage charge : {money(totals['damage_charge'])}")
            print(f"Total due     : {money(totals['total_due'])}")
        self.pause()

    def ui_cancel(self, borrower_id: str) -> None:
        self.header("CANCEL REQUEST / BOOKING")
        cancellable_requests = [
            request
            for request in self.app.requests.values()
            if request.borrower_id == borrower_id and request.status == "PENDING"
        ]
        cancellable_transactions = [
            transaction
            for transaction in self.app.transactions.values()
            if transaction.borrower_id == borrower_id and transaction.status == "BORROWED"
        ]

        records = []

        for request in cancellable_requests:
            item = self.app.items.get(request.item_id)
            item_name = item.name if item else "Unknown item"
            daily_rent = money(item.rental_price_per_day) if item else "₹0"
            records.append(
                (
                    request.request_id,
                    f"Request {request.request_id}",
                    item_name,
                    f"{request.duration_days} day(s)",
                    f"{daily_rent}/day",
                    "Waiting for lender",
                )
            )

        for transaction in cancellable_transactions:
            item = self.app.items.get(transaction.item_id)
            item_name = item.name if item else "Unknown item"
            records.append(
                (
                    transaction.transaction_id,
                    f"Booking {transaction.transaction_id}",
                    item_name,
                    f"{transaction.duration_days} day(s)",
                    f"{money(transaction.daily_rent)}/day",
                    f"Due {transaction.due_date.isoformat()}",
                )
            )

        if not records:
            print("No pending request or cancellable booking.")
            self.pause()
            return

        print("Select what you want to cancel:\n")
        for index, (_, record_type, item_name, duration, rent, status) in enumerate(records, 1):
            print(f"{index}. {record_type}")
            print(f"   Item     : {item_name}")
            print(f"   Duration : {duration}")
            print(f"   Rent     : {rent}")
            print(f"   Status   : {status}\n")

        print("Enter the record number. Enter 0 to go back.")
        index = self.parse_menu_index(self.ask("Choice: "), len(records))
        if index == 0:
            return
        if index == -1:
            print("\n✗ Invalid selection.")
            self.pause()
            return

        record_id = records[index - 1][0]
        ok, result = self.app.cancel_request_or_booking(borrower_id, record_id)
        print(f"\n{'✓' if ok else '✗'} {result}")
        self.pause()

    # --------------------------------------------------------
    # HISTORY
    # --------------------------------------------------------
    def ui_history(self, student_id: str) -> None:
        self.header("BORROWING / LENDING HISTORY")
        history = self.app.get_borrowing_history(student_id)
        if not history:
            print("No borrowing/lending history.")
            self.pause()
            return

        for transaction in history:
            item = self.app.items.get(transaction.item_id)
            item_name = item.name if item else "Unknown item"
            role = "Borrowed" if transaction.borrower_id == student_id else "Lent"
            print(
                f"{transaction.transaction_id} | {role} | {item_name} | "
                f"{transaction.status} | Rent: {money(transaction.rental_amount)}"
            )
        self.pause()

    # --------------------------------------------------------
    # MASTER CAMPUS RESOURCE & AUDIT DASHBOARD (ADMIN PASSKEY)
    # --------------------------------------------------------
    @staticmethod
    def _dash_banner(title: str, emoji: str = "⚡", color: str = "") -> None:
        """Render a vivid full-width banner for dashboard sections."""
        col = color or C.CYAN
        w = 76
        print(f"{col}{C.BOLD}╔{'═' * (w - 2)}╗{C.RESET}")
        label = f" {emoji}  {title}  {emoji} "
        print(f"{col}{C.BOLD}║{label:^{w - 2}}║{C.RESET}")
        print(f"{col}{C.BOLD}╚{'═' * (w - 2)}╝{C.RESET}")

    @staticmethod
    def _kpi_pill(emoji: str, label: str, value, color: str) -> str:
        """Return a coloured KPI pill string."""
        return f"{color}{C.BOLD}╔═ {emoji} {label}: {value} ═╗{C.RESET}"

    def ui_master_dashboard(self, lender_filter: str | None = None) -> None:
        while True:
            # ── Live data pull ─────────────────────────────────────────────
            lender_items      = self.app.get_lender_inventory_report(lender_filter)
            borrower_loans    = self.app.get_borrower_loans_report(lender_filter)
            pending_requests  = self.app.get_pending_borrower_requests_report(lender_filter)
            active_summary    = self.app.get_active_students_summary()

            borrowed_loans       = [t for t in borrower_loans if t["transaction_status"] == "BORROWED"]
            return_pending_loans = [t for t in borrower_loans if t["transaction_status"] == "RETURN_PENDING"]
            completed_loans      = [t for t in borrower_loans if t["transaction_status"] == "COMPLETED"]
            pending_reqs         = [r for r in pending_requests if r.get("request_status") == "PENDING"]
            active_user_cnt      = active_summary.get("total_active", len(active_summary))

            w = 76

            # ── Master banner ──────────────────────────────────────────────
            print()
            self._dash_banner("CAMPUS RESOURCE & AUDIT MASTER DASHBOARD  [DBMS LIVE]",
                              emoji="🛡️", color=C.CYAN)

            # ── System status strip ────────────────────────────────────────
            c_info  = self.app.get_cloud_status()
            c_badge = (f"{C.GREEN}● SUPABASE LIVE{C.RESET}"
                       if c_info.get("configured")
                       else f"{C.YELLOW}○ LOCAL ONLY{C.RESET}")
            filter_pill = (f" {C.DIM}│{C.RESET} {C.YELLOW}🔍 Filter:{C.RESET} {C.BOLD}{lender_filter}{C.RESET}"
                           if lender_filter else "")
            print(
                f" {C.MAGENTA}👑 Authority:{C.RESET} {C.BOLD}Admin{C.RESET}  "
                f"{C.DIM}│{C.RESET}  {C.CYAN}🗄️  Engine:{C.RESET} SQLite 3  "
                f"{C.DIM}│{C.RESET}  ☁️  Cloud: {c_badge}"
                f"{filter_pill}"
            )
            print(f"{C.GRAY}{'─' * w}{C.RESET}")

            # ── Colourful KPI pills (2 rows × 3 pills) ─────────────────────
            def pill(emoji_icon, label, val, fg):
                return f"{fg}{C.BOLD} {emoji_icon} {label}: {C.UNDERLINE}{val}{C.RESET}{fg} {C.RESET}"

            row1 = (
                pill("👥", "Active Users",   active_user_cnt,          C.CYAN)   + "  " +
                pill("📦", "Total Items",    len(lender_items),         C.YELLOW) + "  " +
                pill("🔴", "Borrowed",       len(borrowed_loans),       C.RED)
            )
            row2 = (
                pill("🟡", "Return Pending", len(return_pending_loans), C.YELLOW) + "  " +
                pill("🟢", "Completed",      len(completed_loans),      C.GREEN)  + "  " +
                pill("📬", "Req Pending",    len(pending_reqs),         C.MAGENTA)
            )
            print(f"  {row1}")
            print(f"  {row2}")

            # ── Return-pending alert banner ────────────────────────────────
            if return_pending_loans:
                print(f"\n{C.BG_YELLOW}{C.BOLD}  ⚠️  ATTENTION: {len(return_pending_loans)} RETURN(S) AWAITING LENDER CONFIRMATION  {C.RESET}")
                for r_tx in return_pending_loans:
                    cond_label = r_tx.get("return_condition") or "Submitted"
                    print(
                        f"   {C.YELLOW}▶{C.RESET} Borrower {C.YELLOW}{C.BOLD}{r_tx['borrower_id']}{C.RESET} "
                        f"({r_tx['borrower_name']}) → item "
                        f"{C.CYAN}{C.BOLD}{r_tx['item_id']}{C.RESET} ({r_tx['item_name']})  "
                        f"Cond: {C.RED}{cond_label}{C.RESET}"
                    )
                    print(
                        f"   {C.GRAY}└─{C.RESET} Awaiting Lender "
                        f"{C.YELLOW}{r_tx['lender_id']}{C.RESET} ({r_tx['lender_name']}) to confirm"
                    )
                print(f"{C.GRAY}{'─' * w}{C.RESET}")

            # ╔══════════════════════════════════════════════════════════════╗
            # ║  SECTION 1 — LENDER INVENTORY                              ║
            # ╚══════════════════════════════════════════════════════════════╝
            print()
            print(f"{C.YELLOW}{C.BOLD}╔═══ 📦  SECTION 1  ·  LENDER INVENTORY {'·' * 26}╗{C.RESET}")
            print(f"{C.YELLOW}{C.BOLD}║  Lender ID  │  Lender Name  │  Item  │  Cost/Day  │  Status         ║{C.RESET}")
            print(f"{C.YELLOW}{C.BOLD}╚{'═' * 74}╝{C.RESET}")

            if not lender_items:
                print(f"  {C.GRAY}╌ No items listed in the database yet.{C.RESET}")
            else:
                # Table borders
                T = C.GRAY
                H = C.YELLOW + C.BOLD      # header text colour
                top = f"{T}┌{'─'*12}┬{'─'*15}┬{'─'*19}┬{'─'*13}┬{'─'*12}┐{C.RESET}"
                mid = f"{T}├{'─'*12}┼{'─'*15}┼{'─'*19}┼{'─'*13}┼{'─'*12}┤{C.RESET}"
                bot = f"{T}└{'─'*12}┴{'─'*15}┴{'─'*19}┴{'─'*13}┴{'─'*12}┘{C.RESET}"
                hdr = (
                    f"{T}│{C.RESET} {pad_c('LENDER ID', 10, H)} "
                    f"{T}│{C.RESET} {pad_c('NAME', 13, H)} "
                    f"{T}│{C.RESET} {pad_c('ITEM', 17, H)} "
                    f"{T}│{C.RESET} {pad_c('₹ / DAY', 11, H)} "
                    f"{T}│{C.RESET} {pad_c('STATUS', 10, H)} "
                    f"{T}│{C.RESET}"
                )
                print(top)
                print(hdr)
                print(mid)
                for r in lender_items:
                    stat = r["item_status"]
                    status_col = {"RETURN_PENDING": C.YELLOW+C.BOLD, "BORROWED": C.RED+C.BOLD,
                                  "AVAILABLE": C.GREEN+C.BOLD}.get(stat, C.MAGENTA+C.BOLD)
                    status_icon = {"RETURN_PENDING": "🟡", "BORROWED": "🔴",
                                   "AVAILABLE": "🟢"}.get(stat, "⚪")
                    iname = f"{r['item_id']}: {r['item_name']}"
                    cost  = f"{money(r['cost_per_day'])}/day"
                    print(
                        f"{T}│{C.RESET} {pad_c(r['lender_id'], 10, C.YELLOW+C.BOLD)} "
                        f"{T}│{C.RESET} {pad_c(r['lender_name'], 13, C.WHITE)} "
                        f"{T}│{C.RESET} {pad_c(iname, 17, C.WHITE+C.BOLD)} "
                        f"{T}│{C.RESET} {pad_c(cost, 11, C.GREEN+C.BOLD)} "
                        f"{T}│{C.RESET} {pad_c(status_icon + ' ' + stat[:9], 10, status_col)} "
                        f"{T}│{C.RESET}"
                    )
                print(bot)

            # ╔══════════════════════════════════════════════════════════════╗
            # ║  SECTION 2 — BORROWER LOANS                                ║
            # ╚══════════════════════════════════════════════════════════════╝
            print()
            print(f"{C.MAGENTA}{C.BOLD}╔═══ 🤝  SECTION 2  ·  BORROWER LOANS {'·' * 27}╗{C.RESET}")
            print(f"{C.MAGENTA}{C.BOLD}║  Borrower  │  Item  │  Lender  │  Days  │  Due Date  │  Status      ║{C.RESET}")
            print(f"{C.MAGENTA}{C.BOLD}╚{'═' * 74}╝{C.RESET}")

            if not borrower_loans and not pending_requests:
                print(f"  {C.GRAY}╌ No loans recorded.{C.RESET}")
            else:
                if borrower_loans:
                    T = C.GRAY
                    H = C.MAGENTA + C.BOLD
                    top2 = f"{T}┌{'─'*12}┬{'─'*17}┬{'─'*12}┬{'─'*7}┬{'─'*12}┬{'─'*12}┐{C.RESET}"
                    mid2 = f"{T}├{'─'*12}┼{'─'*17}┼{'─'*12}┼{'─'*7}┼{'─'*12}┼{'─'*12}┤{C.RESET}"
                    bot2 = f"{T}└{'─'*12}┴{'─'*17}┴{'─'*12}┴{'─'*7}┴{'─'*12}┴{'─'*12}┘{C.RESET}"
                    hdr2 = (
                        f"{T}│{C.RESET} {pad_c('BORROWER', 10, H)} "
                        f"{T}│{C.RESET} {pad_c('ITEM', 15, H)} "
                        f"{T}│{C.RESET} {pad_c('LENDER', 10, H)} "
                        f"{T}│{C.RESET} {pad_c('DAYS', 5, H)} "
                        f"{T}│{C.RESET} {pad_c('DUE DATE', 10, H)} "
                        f"{T}│{C.RESET} {pad_c('STATUS', 10, H)} "
                        f"{T}│{C.RESET}"
                    )
                    print(top2)
                    print(hdr2)
                    print(mid2)
                    for b in borrower_loans:
                        tstat = b["transaction_status"]
                        s_col  = {"BORROWED": C.RED+C.BOLD, "RETURN_PENDING": C.YELLOW+C.BOLD,
                                  "COMPLETED": C.GREEN+C.BOLD}.get(tstat, C.WHITE)
                        s_icon = {"BORROWED": "🔴", "RETURN_PENDING": "🟡",
                                  "COMPLETED": "🟢"}.get(tstat, "⚪")
                        s_txt  = {"BORROWED": "BORROWED", "RETURN_PENDING": "RET PEND",
                                  "COMPLETED": "RETURNED"}.get(tstat, tstat)
                        bitem  = f"{b['item_id']}: {b['item_name']}"
                        print(
                            f"{T}│{C.RESET} {pad_c(b['borrower_id'], 10, C.YELLOW+C.BOLD)} "
                            f"{T}│{C.RESET} {pad_c(bitem, 15, C.WHITE+C.BOLD)} "
                            f"{T}│{C.RESET} {pad_c(b['lender_id'], 10, C.CYAN+C.BOLD)} "
                            f"{T}│{C.RESET} {pad_c(str(b['duration_days']), 5, C.YELLOW+C.BOLD)} "
                            f"{T}│{C.RESET} {pad_c(str(b['due_date']), 10, C.WHITE)} "
                            f"{T}│{C.RESET} {pad_c(s_icon + ' ' + s_txt, 10, s_col)} "
                            f"{T}│{C.RESET}"
                        )
                    print(bot2)

                if pending_requests:
                    print(f"\n  {C.BG_YELLOW}{C.BOLD}  🔔  PENDING BORROW REQUESTS  {C.RESET}")
                    for p_req in pending_requests:
                        p_days = p_req["duration_days"]
                        p_rent = money(p_req["cost_per_day"] * p_days)
                        print(
                            f"   {C.YELLOW}▶{C.RESET} Req {C.BOLD}{p_req['request_id']}{C.RESET}:  "
                            f"{C.WHITE}{p_req['borrower_id']} ({p_req['borrower_name']}){C.RESET} "
                            f"wants {C.CYAN}{p_req['item_id']} ({p_req['item_name']}){C.RESET} "
                            f"from {C.YELLOW}{p_req['lender_id']} ({p_req['lender_name']}){C.RESET} "
                            f"— {C.BOLD}{p_days}d{C.RESET} (Est {C.GREEN}{p_rent}{C.RESET}) "
                            f"{C.MAGENTA}[PENDING]{C.RESET}"
                        )

            # ── Admin action footer menu ───────────────────────────────────
            print(f"\n{C.GRAY}{'═' * w}{C.RESET}")
            fa_label = (f"{C.YELLOW}[2] 🧹 Clear Filter{C.RESET}"
                        if lender_filter else f"{C.CYAN}[2] 📋 Ledger Cards{C.RESET}")
            print(
                f"  {C.BOLD}DATA   :{C.RESET}  "
                f"{C.YELLOW}[1] 🔍 Filter Lender{C.RESET}  │  "
                f"{fa_label}  │  "
                f"{C.MAGENTA}[3] 👥 Students{C.RESET}"
            )
            print(
                f"  {C.BOLD}TOOLS  :{C.RESET}  "
                f"{C.GREEN}[4] 🔬 Diagnostics{C.RESET}  │  "
                f"{C.CYAN}[5] ☁️  Cloud Sync{C.RESET}  │  "
                f"{C.DIM}[Enter] ⬅  Back to Menu{C.RESET}"
            )
            print(f"{C.GRAY}{'═' * w}{C.RESET}")

            admin_action = self.ask(f"\n{C.BOLD}Choice:{C.RESET} ").strip()
            if not admin_action:
                return

            if admin_action == "1":
                fi = self.ask("\nEnter Lender AU_ID (or roll number, B to cancel): ").strip()
                if fi.upper() == "B" or not fi:
                    continue
                ok, normalized_id = self.app.normalize_student_input(fi)
                if not ok:
                    print(f"\n{C.RED}✗ {normalized_id}{C.RESET}")
                    self.pause()
                    continue
                lender_filter = normalized_id
                continue

            elif admin_action == "2":
                if lender_filter:
                    lender_filter = None
                    print(f"\n{C.GREEN}✓ Filter cleared — showing full database.{C.RESET}")
                    continue
                else:
                    self.ui_detailed_ledger_cards(borrower_loans)
                    continue

            elif admin_action == "3":
                self.ui_student_directory()
                continue

            elif admin_action == "4":
                self.header("DBMS INTEGRITY & SCHEMA DIAGNOSTICS")
                live_diag = self.app.get_dbms_diagnostics()
                print(f" {C.CYAN}• SQLite File       :{C.RESET} {live_diag['db_path']}")
                print(f" {C.GREEN}• Integrity Check   :{C.RESET} {live_diag['integrity']}")
                print(f" {C.YELLOW}• FK Violations     :{C.RESET} {live_diag['fk_violations']}")
                print(f"\n {C.BOLD}Table Record Counts:{C.RESET}")
                for tbl, cnt in live_diag["counts"].items():
                    print(f"   {C.GRAY}├─{C.RESET} {tbl:<18} : {C.CYAN}{cnt}{C.RESET} record(s)")
                print("=" * 68)
                self.pause()
                continue

            elif admin_action == "5":
                self.ui_cloud_sync_manager()
                continue
            else:
                return

    def ui_student_directory(self) -> None:
        """Displays all registered students, their PIN security status, and campus activity."""
        print()
        self._dash_banner("REGISTERED STUDENT DIRECTORY  &  PIN STATUS",
                          emoji="👥", color=C.CYAN)
        students = self.app.db.load_students() if self.app.db else {}
        if not students:
            print(f"  {C.GRAY}No student records found in database.{C.RESET}")
            self.pause()
            return

        T = C.GRAY
        H = C.CYAN + C.BOLD
        top = f"{T}┌{'─'*13}┬{'─'*20}┬{'─'*20}┬{'─'*20}┐{C.RESET}"
        mid = f"{T}├{'─'*13}┼{'─'*20}┼{'─'*20}┼{'─'*20}┤{C.RESET}"
        bot = f"{T}└{'─'*13}┴{'─'*20}┴{'─'*20}┴{'─'*20}┘{C.RESET}"
        hdr = (
            f"{T}│{C.RESET} {pad_c('STUDENT ID', 11, H)} "
            f"{T}│{C.RESET} {pad_c('FULL NAME', 18, H)} "
            f"{T}│{C.RESET} {pad_c('PIN SECURITY', 18, H)} "
            f"{T}│{C.RESET} {pad_c('CAMPUS ROLE', 18, H)} "
            f"{T}│{C.RESET}"
        )
        print(top)
        print(hdr)
        print(mid)

        for sid, s in sorted(students.items()):
            has_pin = bool(s.get("pin"))
            if has_pin:
                pin_str = pad_c("🔒 PIN PROTECTED", 18, C.GREEN + C.BOLD)
            else:
                pin_str = pad_c("🔓 NO PIN SET", 18, C.YELLOW)

            roles = []
            if any(i.lender_id == sid for i in self.app.items.values()):
                roles.append("📦 Lender")
            if any(t.borrower_id == sid for t in self.app.transactions.values()):
                roles.append("🎒 Borrower")
            role_str = "  ".join(roles) if roles else "👤 Registered"

            print(
                f"{T}│{C.RESET} {pad_c(sid, 11, C.YELLOW + C.BOLD)} "
                f"{T}│{C.RESET} {pad_c(s['name'], 18, C.WHITE + C.BOLD)} "
                f"{T}│{C.RESET} {pin_str} "
                f"{T}│{C.RESET} {pad_c(role_str, 18, C.CYAN)} "
                f"{T}│{C.RESET}"
            )
        print(bot)
        print(f"\n  {C.CYAN}{C.BOLD}Total Registered Students:{C.RESET} {C.WHITE}{len(students)}{C.RESET}")
        self.pause()

    def ui_cloud_sync_manager(self) -> None:
        """Interactive control panel for Supabase PostgreSQL Cloud Sync."""
        while True:
            self.header("☁️  SUPABASE CLOUD SYNCHRONIZATION MANAGER")
            st = self.app.get_cloud_status()
            is_cfg = st.get("configured", False)
            stat_color = C.GREEN if is_cfg else C.YELLOW
            stat_text = "● CONNECTED (Live Dual-Write Active)" if is_cfg else "○ STANDBY (API Key Needed)"

            print(f" {C.BOLD}Cloud Project :{C.RESET} btkwitdwjrlmucdpaudi (nandakishoreraju16-lab)")
            print(f" {C.BOLD}API Endpoint  :{C.RESET} {st.get('url', 'https://btkwitdwjrlmucdpaudi.supabase.co')}")
            print(f" {C.BOLD}API Key Status:{C.RESET} {st.get('masked_key', 'Not Set')}")
            print(f" {C.BOLD}Live Status   :{C.RESET} {stat_color}{stat_text}{C.RESET}")
            print(f"{C.GRAY}" + "─" * 68 + f"{C.RESET}")
            print(f"  {C.YELLOW}1.{C.RESET} ⚡ Test Supabase Cloud Connection / Ping")
            print(f"  {C.CYAN}2.{C.RESET} 🚀 Push All Local Tables to Supabase (Full Cloud Sync)")
            print(f"  {C.MAGENTA}3.{C.RESET} 🧹 Prune 93 Empty Placeholder Students in Supabase Cloud")
            print(f"  {C.GREEN}4.{C.RESET} 🔑 Configure / Update Supabase API Key (.env)")
            print(f"  {C.WHITE}5.{C.RESET} 📄 View 1-Click SQL Script for Supabase Web SQL Editor")
            print(f"  {C.GRAY}6.{C.RESET} ⬅️  Back to Master Dashboard")

            sub_choice = self.ask(f"\n{C.BOLD}Enter choice (1-6):{C.RESET} ").strip()
            if sub_choice == "1":
                print("\nPinging Supabase Cloud...")
                ok, msg = self.app.test_cloud_connection()
                if ok:
                    print(f"\n{C.GREEN}✓ {msg}{C.RESET}")
                else:
                    print(f"\n{C.RED}✗ {msg}{C.RESET}")
                self.pause()
            elif sub_choice == "2":
                print("\nUploading local database tables to Supabase Cloud...")
                ok, msg, counts = self.app.sync_push_to_cloud()
                if ok:
                    print(f"\n{C.GREEN}✓ {msg}{C.RESET}")
                    for tbl, c in counts.items():
                        print(f"  {C.GRAY}├─{C.RESET} {tbl:<18} : {C.CYAN}{c}{C.RESET} row(s) synced")
                else:
                    print(f"\n{C.RED}✗ {msg}{C.RESET}")
                self.pause()
            elif sub_choice == "3":
                print("\nPruning empty student rows in Supabase Cloud...")
                ok, msg, deleted = self.app.prune_cloud_students()
                if ok:
                    print(f"\n{C.GREEN}✓ {msg}{C.RESET}")
                    print(f"  Cloud students table now matches active local students ({deleted} removed).")
                else:
                    print(f"\n{C.RED}✗ {msg}{C.RESET}")
                self.pause()
            elif sub_choice == "4":
                print("\nEnter your Supabase 'anon' public key or service role key.")
                print("Get it from: Supabase Dashboard > Project Settings > API")
                new_key = self.ask("Enter Key (or B to cancel): ").strip()
                if new_key.upper() == "B" or not new_key:
                    continue
                ok, msg = self.app.configure_cloud("https://btkwitdwjrlmucdpaudi.supabase.co", new_key)
                if ok:
                    print(f"\n{C.GREEN}✓ API Key saved to .env! Connected successfully.{C.RESET}")
                else:
                    print(f"\n{C.RED}✗ {msg}{C.RESET}")
                self.pause()
            elif sub_choice == "5":
                self.header("1-CLICK SQL CLEANUP FOR SUPABASE WEB EDITOR")
                print(f" {C.CYAN}Step 1:{C.RESET} Open Supabase SQL Editor in browser:")
                print(f"        {C.UNDERLINE}https://supabase.com/dashboard/project/btkwitdwjrlmucdpaudi/sql/new{C.RESET}")
                print(f"\n {C.CYAN}Step 2:{C.RESET} Run this SQL to wipe the 93 empty placeholder rows:\n")
                print(f"{C.YELLOW}DELETE FROM public.students")
                print(f"WHERE (pin = '' OR pin IS NULL OR pin = 'EMPTY')")
                print(f"  AND student_id NOT IN (SELECT lender_id FROM public.items)")
                print(f"  AND student_id NOT IN (SELECT borrower_id FROM public.borrow_requests)")
                print(f"  AND student_id NOT IN (SELECT lender_id FROM public.borrow_requests)")
                print(f"  AND student_id NOT IN (SELECT borrower_id FROM public.transactions)")
                print(f"  AND student_id NOT IN (SELECT lender_id FROM public.transactions);{C.RESET}\n")
                print(f" {C.CYAN}Step 3:{C.RESET} Go back to Table Editor -> students. Only 7 rows will remain!")
                self.pause()
            elif sub_choice in ("6", "B", "BACK", ""):
                return

    def ui_detailed_ledger_cards(self, borrower_loans: list[dict]) -> None:
        """Renders comprehensive loan transaction cards with settlement financials."""
        print()
        self._dash_banner("DETAILED TRANSACTION LEDGER  &  SETTLEMENT CARDS",
                          emoji="📋", color=C.MAGENTA)
        if not borrower_loans:
            print(f"  {C.GRAY}No transactions recorded yet.{C.RESET}")
        else:
            for idx, b_row in enumerate(borrower_loans, 1):
                tx_id    = b_row["transaction_id"]
                bid      = b_row["borrower_id"]
                bname    = b_row["borrower_name"]
                lid      = b_row["lender_id"]
                lname    = b_row["lender_name"]
                iid      = b_row["item_id"]
                iname    = b_row["item_name"]
                days     = b_row["duration_days"]
                d_rent   = money(b_row["daily_rent"])
                tot_rent = money(b_row["rental_amount"])
                s_date   = b_row["start_date"]
                d_date   = b_row["due_date"]
                t_stat   = b_row["transaction_status"]

                stat_col = {"BORROWED": C.RED, "RETURN_PENDING": C.YELLOW,
                            "COMPLETED": C.GREEN}.get(t_stat, C.WHITE)
                stat_icon = {"BORROWED": "🔴", "RETURN_PENDING": "🟡",
                             "COMPLETED": "🟢"}.get(t_stat, "⚪")

                bar = "─" * 66
                print(f"\n{C.MAGENTA}{C.BOLD}┌─ 📄 TRANSACTION #{idx}  [{tx_id}] {bar[:40]}─╮{C.RESET}")
                print(f"{C.MAGENTA}│{C.RESET}  {C.YELLOW}🎒 Borrower   :{C.RESET} {C.BOLD}{bid}{C.RESET} — {bname}")
                print(f"{C.MAGENTA}│{C.RESET}  {C.CYAN}📦 Item       :{C.RESET} {C.BOLD}{iid}{C.RESET} ({iname})  @  {C.GREEN}{d_rent}/day{C.RESET}")
                print(f"{C.MAGENTA}│{C.RESET}  {C.MAGENTA}👑 Lender     :{C.RESET} {C.BOLD}{lid}{C.RESET} — {lname}")
                print(f"{C.MAGENTA}│{C.RESET}  {C.WHITE}📅 Duration   :{C.RESET} {C.BOLD}{days} Day(s){C.RESET}   {s_date}  ➔  Due: {C.YELLOW}{d_date}{C.RESET}")
                print(f"{C.MAGENTA}│{C.RESET}  {stat_col}📊 Loan Status:{C.RESET} {stat_col}{C.BOLD}{stat_icon} {t_stat}{C.RESET}")

                if t_stat == "BORROWED":
                    print(f"{C.MAGENTA}│{C.RESET}  {C.GREEN}💰 Financials :{C.RESET}"
                          f"  Rental: {C.GREEN}{C.BOLD}{tot_rent}{C.RESET}"
                          f"  │  Lender Net: {C.GREEN}{money(b_row['lender_earnings'])}{C.RESET}")
                elif t_stat == "RETURN_PENDING":
                    cond = b_row.get("return_condition") or "Submitted"
                    print(f"{C.MAGENTA}│{C.RESET}  {C.YELLOW}⚠️  Action     :{C.RESET}"
                          f"  Return pending — Condition: '{C.BOLD}{cond}{C.RESET}'"
                          f"  Awaiting Lender {C.YELLOW}{lid}{C.RESET}")
                elif t_stat == "COMPLETED":
                    ret_date = b_row.get("returned_on") or "Settled"
                    print(f"{C.MAGENTA}│{C.RESET}  {C.GREEN}✅ Settled on :{C.RESET} {ret_date}")
                    print(f"{C.MAGENTA}│{C.RESET}  {C.GREEN}💰 Financials :{C.RESET}"
                          f"  Total: {C.GREEN}{C.BOLD}{tot_rent}{C.RESET}"
                          f"  │  Late Fee: {C.YELLOW}{money(b_row['late_fee'])}{C.RESET}"
                          f"  │  Damage: {C.RED}{money(b_row['damage_charge'])}{C.RESET}")
                print(f"{C.MAGENTA}╰{'─' * 66}╯{C.RESET}")
        print()
        self.pause()

    # --------------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------------
    def run(self) -> None:
        admin_passkey = "NANDU1216@#$"

        while True:
            self.header("BORROW INSTEAD OF BUY")
            print(f"  {C.YELLOW}1.{C.RESET} 📦 Lender")
            print(f"  {C.CYAN}2.{C.RESET} 🎒 Borrower")
            print(f"  {C.MAGENTA}3.{C.RESET} 🛡️  Admin Dashboard")
            print(f"  {C.GRAY}4.{C.RESET} 🚪 Exit")
            raw_choice = self.ask(f"\n{C.BOLD}Enter choice:{C.RESET} ")
            choice = raw_choice.strip()

            # Direct secret shortcut if typed at main prompt
            if choice.upper() == admin_passkey:
                if choice != admin_passkey:
                    print(f"\n{C.YELLOW}[AUTOCORRECT] Detected passkey '{choice}' -> Converting to uppercase: '{admin_passkey}'{C.RESET}")
                print(f"{C.GREEN}✓ Master Passkey Accepted! Accessing Database Admin Dashboard...{C.RESET}\n")
                self.ui_master_dashboard()
                continue

            if choice == "1":
                student_id = self.verify_role("Lender")
                if student_id:
                    self.lender_menu(student_id)
            elif choice == "2":
                student_id = self.verify_role("Borrower")
                if student_id:
                    self.borrower_menu(student_id)
            elif choice in ("3", "ADMIN", "DASHBOARD"):
                passkey = self.ask_password("Enter Admin Password: ").strip()
                if passkey.upper() == admin_passkey:
                    if passkey != admin_passkey:
                        print(f"{C.YELLOW}[AUTOCORRECT] Detected passkey '{passkey}' -> Converting to uppercase: '{admin_passkey}'{C.RESET}")
                    print(f"{C.GREEN}✓ Master Passkey Accepted! Accessing Database Admin Dashboard...{C.RESET}\n")
                    self.ui_master_dashboard()
                else:
                    print(f"\n{C.RED}✗ Invalid Password. Access Denied.{C.RESET}")
                    self.pause()
            elif choice in ("4", "EXIT", "QUIT", "Q"):
                print(f"\n{C.CYAN}Goodbye!{C.RESET}")
                return
            else:
                print(f"\n{C.RED}✗ Invalid menu choice. Choose 1 to 4.{C.RESET}")



if __name__ == "__main__":
    BorrowInsteadOfBuyCLI().run()

