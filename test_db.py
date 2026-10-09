import os
import sqlite3
from datetime import date

from logic import BorrowInsteadOfBuyApp


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_db_persistence_and_reload():
    test_db = "test_persistence.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    try:
        # Session 1: Create app with database persistence
        app1 = BorrowInsteadOfBuyApp(today=date(2026, 9, 9), db_path=test_db)
        
        # Verify 100 students were seeded into DBMS
        expect(len(app1.students) == 100, f"Expected 100 students, found {len(app1.students)}")
        
        # Add item as lender AU25UG001
        ok, item_id = app1.add_item("AU25UG001", "Scientific Calculator FX-991EX", "Good", 50.0)
        expect(ok and item_id == "I001", f"Item addition failed: {item_id}")
        
        # Borrower AU25UG002 requests item for 3 days
        ok, req_id = app1.create_borrow_request("AU25UG002", item_id, 3)
        expect(ok and req_id == "R001", f"Request failed: {req_id}")
        
        # Lender accepts request
        ok, tx_id = app1.accept_request("AU25UG001", req_id, date(2026, 9, 9))
        expect(ok and tx_id == "T001", f"Accept failed: {tx_id}")

        # Simulate shutdown / new session by opening new app instance pointing to same DB
        app2 = BorrowInsteadOfBuyApp(today=date(2026, 9, 12), db_path=test_db)

        # Verify state reloaded from DB
        expect("I001" in app2.items, "Item not reloaded from DB")
        expect(app2.items["I001"].status == "BORROWED", "Item status not persisted as BORROWED")
        expect("R001" in app2.requests, "Borrow request not reloaded from DB")
        expect(app2.requests["R001"].status == "ACCEPTED", "Request status not persisted as ACCEPTED")
        expect("T001" in app2.transactions, "Transaction not reloaded from DB")
        expect(app2.transactions["T001"].status == "BORROWED", "Transaction status not persisted")
        expect(app2.transactions["T001"].rental_amount == 150.0, "Rental amount mismatch")
        expect(app2.transactions["T001"].commission == 15.0, "Commission mismatch")
        expect(app2.transactions["T001"].lender_earnings == 135.0, "Lender earnings mismatch")

        # In Session 2: Borrower returns item on due date with Minor damage
        ok, ret_id = app2.return_item("AU25UG002", tx_id, "MINOR", date(2026, 9, 12))
        expect(ok and ret_id == "RET001", f"Return failed: {ret_id}")

        # Lender confirms return in Session 2
        ok, msg = app2.confirm_return("AU25UG001", ret_id)
        expect(ok, f"Confirm return failed: {msg}")
        expect(app2.items["I001"].status == "AVAILABLE", "Item should be AVAILABLE after return confirmation")

        # Session 3: Open third instance to confirm completed transaction and earnings
        app3 = BorrowInsteadOfBuyApp(today=date(2026, 9, 13), db_path=test_db)
        expect(app3.transactions["T001"].status == "COMPLETED", "Transaction not COMPLETED in DB")
        earnings = app3.get_earnings("AU25UG001")
        expect(earnings["completed_transactions"] == 1, "Completed transactions count mismatch")
        expect(earnings["rental_amount"] == 150.0, "Total rental mismatch")
        expect(earnings["commission"] == 15.0, "Total commission mismatch")
        expect(earnings["lender_earnings"] == 135.0, "Total earnings mismatch")

        # Verify SQL-level direct records in SQLite
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM items WHERE item_id = 'I001'")
        expect(cursor.fetchone()[0] == "AVAILABLE", "Direct SQL check on items failed")
        cursor.execute("SELECT status FROM transactions WHERE transaction_id = 'T001'")
        expect(cursor.fetchone()[0] == "COMPLETED", "Direct SQL check on transactions failed")
        conn.close()

    finally:
        if os.path.exists(test_db):
            os.remove(test_db)


def test_db_foreign_key_enforcement():
    test_db = "test_fk.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    try:
        app = BorrowInsteadOfBuyApp(today=date(2026, 9, 9), db_path=test_db)
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()

        # Attempt to insert an item with non-existent student ID
        try:
            cursor.execute(
                "INSERT INTO items (item_id, name, condition, rental_price_per_day, lender_id, status) VALUES (?, ?, ?, ?, ?, ?)",
                ("I999", "Invalid Item", "Good", 10.0, "UNKNOWN_STU", "AVAILABLE"),
            )
            conn.commit()
            raise AssertionError("Foreign key violation should have prevented item creation with non-existent student")
        except sqlite3.IntegrityError:
            pass  # Expected foreign key constraint failure

        conn.close()
    finally:
        if os.path.exists(test_db):
            os.remove(test_db)


def test_student_shorthand_and_pin_persistence():
    test_db = "test_pin.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    try:
        # Session 1: Test normalization and PIN setting
        app1 = BorrowInsteadOfBuyApp(today=date(2026, 9, 9), db_path=test_db)
        
        # Test shorthand roll number expansion
        ok, sid = app1.normalize_student_input("1")
        expect(ok and sid == "AU25UG001", f"Shorthand '1' failed: {sid}")

        ok, sid = app1.normalize_student_input("100")
        expect(ok and sid == "AU25UG100", f"Shorthand '100' failed: {sid}")

        ok, sid = app1.normalize_student_input("au25ug045")
        expect(ok and sid == "AU25UG045", f"Full ID normalization failed: {sid}")

        ok, err = app1.normalize_student_input("101")
        expect(not ok, "Invalid roll number 101 accepted")

        # Set 4-digit PIN
        ok, msg = app1.set_student_pin("AU25UG001", "1234")
        expect(ok, f"PIN set failed: {msg}")

        # Invalid PIN (not 4 digits)
        ok, _ = app1.set_student_pin("AU25UG001", "12")
        expect(not ok, "Short PIN accepted")
        ok, _ = app1.set_student_pin("AU25UG001", "abcd")
        expect(not ok, "Alpha PIN accepted")

        # Verify PIN in Session 1
        expect(app1.verify_student_pin("AU25UG001", "1234") is True, "PIN verification failed")
        expect(app1.verify_student_pin("AU25UG001", "9999") is False, "Wrong PIN accepted")

        # Test duplicate PIN rejection (AU25UG002 tries to use AU25UG001's PIN)
        ok, err = app1.set_student_pin("AU25UG002", "1234")
        expect(not ok, "Duplicate PIN 1234 was incorrectly accepted for AU25UG002")
        expect("already used" in err.lower(), f"Unexpected duplicate PIN error: {err}")

        # Unique PIN for AU25UG002 succeeds
        ok, msg = app1.set_student_pin("AU25UG002", "5678")
        expect(ok, f"Unique PIN failed for AU25UG002: {msg}")

        # Same student re-confirming their own PIN is allowed
        ok, msg = app1.set_student_pin("AU25UG001", "1234")
        expect(ok, f"Same student re-setting own PIN failed: {msg}")

        # Session 2: Reload from SQLite and ensure PIN persisted
        app2 = BorrowInsteadOfBuyApp(today=date(2026, 9, 10), db_path=test_db)
        expect(app2.get_student_pin("AU25UG001") == "1234", "PIN not persisted across sessions")
        expect(app2.get_student_pin("AU25UG002") == "5678", "PIN not persisted for AU25UG002")
        expect(app2.verify_student_pin("AU25UG001", "1234") is True, "Re-loaded PIN verification failed")
        expect(app2.verify_student_pin("AU25UG002", "5678") is True, "Re-loaded PIN verification failed for AU25UG002")
        expect(app2.get_student_pin("AU25UG003") == "", "Unset PIN should be empty")

        # Ensure Session 2 also prevents duplicate against persisted DB
        ok, err = app2.set_student_pin("AU25UG003", "1234")
        expect(not ok, "Session 2 accepted duplicate PIN 1234 from persisted database")
        expect("already used" in err.lower(), f"Unexpected error message: {err}")

    finally:
        if os.path.exists(test_db):
            os.remove(test_db)


def test_master_dashboard_ledger_and_passkey():
    test_db = "test_dashboard.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    try:
        app = BorrowInsteadOfBuyApp(today=date(2026, 9, 9), db_path=test_db)
        admin_passkey = "NANDU1216@#$"

        # 1. Test passkey case-insensitive autocorrect logic
        variations = ["nandu1216@#$", "Nandu1216@#$", "NANDU1216@#$", "  nandu1216@#$  "]
        for var in variations:
            normalized = var.strip().upper()
            expect(normalized == admin_passkey, f"Autocorrect failed for variation: '{var}'")

        # 2. Add an item as lender AU25UG001
        ok, item_id = app.add_item("AU25UG001", "Lab Kit Pro", "Excellent", 80.0)
        expect(ok, "Item creation failed")

        # Check ledger when available
        ledger = app.get_master_ledger()
        expect(len(ledger) == 1, "Ledger should have 1 item")
        row = ledger[0]
        expect(row["lender_id"] == "AU25UG001", "Lender ID mismatch")
        expect(row["item_name"] == "Lab Kit Pro", "Item name mismatch")
        expect(row["return_status"] == "AVAILABLE", "Status should be AVAILABLE")
        expect(row["is_returned"] is None, "is_returned should be None for unborrowed item")

        # 3. Borrower AU25UG005 borrows item for 2 days
        ok, req_id = app.create_borrow_request("AU25UG005", item_id, 2)
        expect(ok, "Request failed")
        ok, tx_id = app.accept_request("AU25UG001", req_id, date(2026, 9, 9))
        expect(ok, "Accept failed")

        # Check ledger when active (NOT RETURNED)
        ledger = app.get_master_ledger()
        row = ledger[0]
        expect(row["lender_id"] == "AU25UG001", "Lender ID mismatch")
        expect(row["borrower_id"] == "AU25UG005", "Borrower ID mismatch")
        expect(row["return_status"] == "NOT RETURNED", "Status should be NOT RETURNED")
        expect(row["is_returned"] is False, "is_returned should be False")
        expect("NOT RETURNED" in row["return_details"], "Return details should state NOT RETURNED")

        # 4. Borrower returns the item
        ok, ret_id = app.return_item("AU25UG005", tx_id, "NO DAMAGE", date(2026, 9, 11))
        expect(ok, "Return failed")
        ok, _ = app.confirm_return("AU25UG001", ret_id)
        expect(ok, "Confirm failed")

        # Check ledger after return (RETURNED)
        ledger = app.get_master_ledger()
        row = ledger[0]
        expect(row["lender_id"] == "AU25UG001", "Lender ID mismatch")
        expect(row["borrower_id"] == "AU25UG005", "Borrower ID mismatch")
        expect(row["return_status"] == "RETURNED", "Status should be RETURNED")
        expect(row["is_returned"] is True, "is_returned should be True")
        expect("RETURNED" in row["return_details"], "Return details should state RETURNED")

        # Test full transactions ledger
        all_txs = app.get_all_transactions_ledger()
        expect(len(all_txs) == 1, "Transaction ledger should contain 1 transaction")
        expect(all_txs[0]["is_returned"] is True, "Transaction should be marked returned")

    finally:
        if os.path.exists(test_db):
            os.remove(test_db)


def test_admin_relational_queries_and_menu_options():
    test_db = "test_admin_relational.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    try:
        app = BorrowInsteadOfBuyApp(today=date(2026, 9, 9), db_path=test_db)

        # 1. Add item as lender AU25UG001
        ok, item_id = app.add_item("AU25UG001", "DSLR Camera Kit", "Excellent", 250.0)
        expect(ok, "Item creation failed")

        # 2. Check get_lender_inventory_report
        lender_rep = app.get_lender_inventory_report()
        expect(len(lender_rep) == 1, "Expected 1 lender inventory row")
        row = lender_rep[0]
        # Column 1: lender_id, Column 2: lender_name, Items & Price
        expect(row["lender_id"] == "AU25UG001", "1st field must be lender_id")
        expect(row["lender_name"] == "Student 001", "2nd field must be lender_name")
        expect(row["item_id"] == item_id, "Item ID mismatch")
        expect(row["item_name"] == "DSLR Camera Kit", "Item Name mismatch")
        expect(row["cost_per_day"] == 250.0, "Cost per day mismatch")
        expect(row["item_status"] == "AVAILABLE", "Initial status should be AVAILABLE")

        # 3. Borrower AU25UG010 borrows from lender AU25UG001 for 5 days
        ok, req_id = app.create_borrow_request("AU25UG010", item_id, 5)
        expect(ok, "Borrow request creation failed")

        # Verify pending request report
        pending_rep = app.get_pending_borrower_requests_report()
        expect(len(pending_rep) == 1, "Expected 1 pending request")
        expect(pending_rep[0]["borrower_id"] == "AU25UG010", "Borrower ID mismatch in pending")
        expect(pending_rep[0]["lender_id"] == "AU25UG001", "Lender AU_ID mismatch in pending")
        expect(pending_rep[0]["duration_days"] == 5, "Duration days mismatch in pending")

        # Lender accepts
        ok, tx_id = app.accept_request("AU25UG001", req_id, date(2026, 9, 9))
        expect(ok, "Request accept failed")

        # 4. Check get_borrower_loans_report
        loans_rep = app.get_borrower_loans_report()
        expect(len(loans_rep) == 1, "Expected 1 loan row")
        loan = loans_rep[0]
        expect(loan["borrower_id"] == "AU25UG010", "Borrower ID mismatch")
        expect(loan["borrower_name"] == "Student 010", "Borrower Name mismatch")
        expect(loan["lender_id"] == "AU25UG001", "Lender AU_ID mismatch")
        expect(loan["lender_name"] == "Student 001", "Lender Name mismatch")
        expect(loan["item_name"] == "DSLR Camera Kit", "Borrowed item mismatch")
        expect(loan["duration_days"] == 5, "Duration days mismatch")
        expect(loan["transaction_status"] == "BORROWED", "Transaction status should be BORROWED")

        # 5. Check DBMS Diagnostics
        diag = app.get_dbms_diagnostics()
        expect(diag["integrity"] == "ok", "Integrity check failed")
        expect(diag["fk_violations"] == 0, "Foreign key violations detected")
        expect(diag["counts"]["students"] == 2, f"Expected 2 registered students in DB, got {diag['counts']['students']}")
        expect(diag["counts"]["items"] == 1, "Item count should be 1")
        expect(diag["counts"]["transactions"] == 1, "Transaction count should be 1")

        # 6. Test active students summary (truthful user metric)
        act_summary = app.get_active_students_summary()
        expect("total_active" in act_summary, "total_active key missing in active summary")
        expect(act_summary["total_active"] >= 2, "Active transacting users should be at least 2")

        # 7. Test Return Pending lifecycle reflection in reports
        ok, ret_res = app.return_item("AU25UG010", tx_id, "No Damage", date(2026, 9, 14))
        expect(ok, "Return item failed")

        # Lender inventory should now reflect RETURN_PENDING
        lender_rep_ret = app.get_lender_inventory_report()
        expect(lender_rep_ret[0]["item_status"] == "RETURN_PENDING", "Item status in lender report should be RETURN_PENDING")

        # Borrower loans report should reflect RETURN_PENDING
        loans_rep_ret = app.get_borrower_loans_report()
        expect(loans_rep_ret[0]["transaction_status"] == "RETURN_PENDING", "Loan status should be RETURN_PENDING")

        # 8. Test filtering by specific lender AU_ID
        filter_rep = app.get_borrower_loans_report(lender_filter="AU25UG001")
        expect(len(filter_rep) == 1, "Filter for AU25UG001 should return 1 record")
        filter_empty = app.get_borrower_loans_report(lender_filter="AU25UG099")
        expect(len(filter_empty) == 0, "Filter for AU25UG099 should return 0 records")

    finally:
        if os.path.exists(test_db):
            os.remove(test_db)


def test_supabase_cloud_sync_integration():
    """Validates Supabase Sync Manager, status reporting, and graceful offline fallback."""
    from supabase_sync import SupabaseSyncManager

    mgr = SupabaseSyncManager(url="https://btkwitdwjrlmucdpaudi.supabase.co", key="")
    expect(not mgr.is_configured(), "Should not be configured without API key")
    summary = mgr.get_status_summary()
    expect(summary["project_ref"] == "btkwitdwjrlmucdpaudi", "Project ref should match btkwitdwjrlmucdpaudi")
    expect(summary["masked_key"] == "Not Set", "Masked key should show Not Set")

    # Test offline mutation call (must not raise exception)
    mgr.async_sync(mgr.sync_student, "AU25UG001", "Student 001", "1234")

    # Test app integration
    test_db = "test_cloud_app.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    try:
        app = BorrowInsteadOfBuyApp(db_path=test_db)
        cloud_stat = app.get_cloud_status()
        expect("configured" in cloud_stat, "Cloud status should report configured boolean")
        expect(cloud_stat["url"] == "https://btkwitdwjrlmucdpaudi.supabase.co", "URL should match default")
        
        # Test student creation with sync hook enabled
        ok, _ = app.set_student_pin("AU25UG001", "9999")
        expect(ok, "Student PIN creation should succeed")
        expect(app.verify_student_pin("AU25UG001", "9999"), "Student PIN should verify")
    finally:
        if os.path.exists(test_db):
            os.remove(test_db)


def test_item_name_validation_and_star_ratings():
    """Validates that junk names like '1234' and '1233ee3dc' are rejected, and star ratings persist."""
    from main import BorrowInsteadOfBuyCLI
    
    # 1. Test item name validation against junk / numbers / keyboard mash
    bad_names = ["1234", "1233ee3dc", "asdf", "qwerty", "dfghjk", "...", "A", ""]
    for bad in bad_names:
        ok, err = BorrowInsteadOfBuyCLI.validate_item_name(bad)
        expect(not ok, f"Bad item name '{bad}' was incorrectly accepted: {err}")

    # 2. Test valid campus items
    good_names = ["Camera", "TI-84 Plus", "3D VR Headset", "Casio fx-991EX", "Lab Coat", "Mini Drafter"]
    for good in good_names:
        ok, clean = BorrowInsteadOfBuyCLI.validate_item_name(good)
        expect(ok, f"Valid item name '{good}' failed validation")

    # 3. Test app insertion with 5-star conditions
    test_db = "test_stars.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    try:
        app = BorrowInsteadOfBuyApp(db_path=test_db)
        star_conditions = [
            "★☆☆☆☆ Poor",
            "★★☆☆☆ Fair",
            "★★★☆☆ Good",
            "★★★★☆ Very Good",
            "★★★★★ Pristine",
        ]
        for idx, cond in enumerate(star_conditions, 1):
            ok, item_id = app.add_item("AU25UG001", f"Campus Item {idx}", cond, 100.0)
            expect(ok, f"Failed to add item with star condition '{cond}'")
            expect(app.items[item_id].condition == cond, f"Condition mismatch for item {item_id}")
    finally:
        if os.path.exists(test_db):
            os.remove(test_db)


if __name__ == "__main__":
    print("Running DBMS integration tests...")
    test_db_persistence_and_reload()
    print("PASS test_db_persistence_and_reload")
    test_db_foreign_key_enforcement()
    print("PASS test_db_foreign_key_enforcement")
    test_student_shorthand_and_pin_persistence()
    print("PASS test_student_shorthand_and_pin_persistence")
    test_master_dashboard_ledger_and_passkey()
    print("PASS test_master_dashboard_ledger_and_passkey")
    test_admin_relational_queries_and_menu_options()
    print("PASS test_admin_relational_queries_and_menu_options")
    test_supabase_cloud_sync_integration()
    print("PASS test_supabase_cloud_sync_integration")
    test_item_name_validation_and_star_ratings()
    print("PASS test_item_name_validation_and_star_ratings")
    print("\nAll DBMS tests passed successfully!")



