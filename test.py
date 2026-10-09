from datetime import date

from logic import (
    BorrowInsteadOfBuyApp,
    calculate_commission,
    calculate_damage_charge,
    calculate_late_fee,
    calculate_lender_earnings,
    calculate_rental,
    parse_positive_float,
    parse_positive_int,
    validate_student_id,
)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_test_app(today: date = date(2026, 9, 9)) -> BorrowInsteadOfBuyApp:
    app = BorrowInsteadOfBuyApp(today=today)
    for lender_id, name, condition, price in [
        ("AU25UG001", "Scientific Calculator", "Good", 100.0),
        ("AU25UG045", "DSLR Camera", "Good", 500.0),
        ("AU25UG078", "Projector", "Excellent", 300.0),
    ]:
        ok, item_id = app.add_item(lender_id, name, condition, price)
        expect(ok, f"Test fixture item failed: {item_id}")
    return app


def test_student_id_validation_group():
    valid = ["AU25UG001", "AU25UG100", "au25ug028"]
    invalid = ["", "001", "100", "AU25UG000", "AU25UG101", "AU24UG001", "AU25UG01", "AU25UG1A1", "AU25UG999"]
    for value in valid:
        ok, result = validate_student_id(value)
        expect(ok, f"Valid ID rejected: {value}")
        expect(result.startswith("AU25UG"), f"Normalization failed: {value}")
    for value in invalid:
        ok, _ = validate_student_id(value)
        expect(not ok, f"Invalid ID accepted: {value}")


def test_unknown_student_id():
    app = BorrowInsteadOfBuyApp(today=date(2026, 9, 9))
    app.students.pop("AU25UG100")
    ok, msg = app.verify_student_id("AU25UG100")
    expect(not ok and "unknown" in msg.lower(), "Unknown ID was accepted")


def test_item_id_is_generated_and_unique():
    app = BorrowInsteadOfBuyApp(today=date(2026, 9, 9))

    ok, item_id_1 = app.add_item("AU25UG001", "Book", "Good", 20)
    expect(ok and item_id_1 == "I001", f"First generated ID incorrect: {item_id_1}")

    ok, item_id_2 = app.add_item("AU25UG001", "Camera", "Good", 100)
    expect(ok and item_id_2 == "I002", f"Second generated ID incorrect: {item_id_2}")

    ok, item_id_3 = app.add_item("AU25UG045", "Calculator", "Excellent", 30)
    expect(ok and item_id_3 == "I003", f"Third generated ID incorrect: {item_id_3}")

    expect(len({item_id_1, item_id_2, item_id_3}) == 3, "Generated Item IDs are duplicated")
    expect(all(item_id.startswith("I") and item_id[1:].isdigit() for item_id in app.items), "Generated Item ID format is wrong")


def test_item_and_price_validation():
    app = BorrowInsteadOfBuyApp(today=date(2026, 9, 9))
    ok, item_id = app.add_item("AU25UG001", "Book", "Good", 20)
    expect(ok, item_id)
    item = app.items[item_id]
    expect(item.status == "AVAILABLE", "New item should be AVAILABLE")
    expect(item.item_id == "I001", "Item ID should be generated")
    expect(not hasattr(item, "location"), "Location should not exist")
    expect(not hasattr(item, "category"), "Category should not exist")
    expect(not hasattr(item, "description"), "Description should not exist")
    expect(not hasattr(item, "purchase_price"), "Purchase price should not exist")

    for bad_price in [0, -5, -0.1]:
        ok, msg = app.add_item("AU25UG001", "X", "Good", bad_price)
        expect(not ok and "positive" in msg.lower(), f"Bad price accepted: {bad_price}")

    ok, msg = app.add_item("AU25UG001", "1234", "Good", 50)
    expect(not ok, "Purely numeric item name '1234' should be rejected")


def test_input_parsers():
    expect(parse_positive_float("500") == 500.0, "Positive float parser failed")
    expect(parse_positive_float("0") is None, "Zero float accepted")
    expect(parse_positive_float("abc") is None, "Text float accepted")
    expect(parse_positive_int("3") == 3, "Positive int parser failed")
    expect(parse_positive_int("0") is None, "Zero int accepted")
    expect(parse_positive_int("abc") is None, "Text int accepted")


def setup_transaction(price: float = 500.0, duration: int = 3):
    app = BorrowInsteadOfBuyApp(today=date(2026, 9, 9))
    ok, item_id = app.add_item("AU25UG045", "Test Camera", "Good", price)
    expect(ok, f"add item failed: {item_id}")
    ok, request_id = app.create_borrow_request("AU25UG001", item_id, duration)
    expect(ok, f"request failed: {request_id}")
    ok, tx_id = app.accept_request("AU25UG045", request_id, date(2026, 9, 9))
    expect(ok, f"accept failed: {tx_id}")
    return app, tx_id


def test_rental_calculation():
    expect(calculate_rental(500, 3) == 1500, "Rental calculation failed")
    expect(calculate_commission(1500) == 150, "Commission calculation failed")
    expect(calculate_lender_earnings(1500) == 1350, "Lender earnings failed")


def test_borrow_request_duration_and_unavailable_item():
    app = make_test_app()
    item_id = "I002"
    ok, msg = app.create_borrow_request("AU25UG001", item_id, 0)
    expect(not ok, "Zero duration accepted")
    ok, msg = app.create_borrow_request("AU25UG001", item_id, -1)
    expect(not ok, "Negative duration accepted")
    ok, req_id = app.create_borrow_request("AU25UG001", item_id, 2)
    expect(ok, f"Valid request failed: {req_id}")
    expect(app.items[item_id].status == "REQUESTED", "Item should be REQUESTED")
    ok, _ = app.create_borrow_request("AU25UG078", item_id, 2)
    expect(not ok, "Unavailable item request should fail")


def test_lender_accept_or_reject_request():
    app = make_test_app()
    ok, req_id = app.create_borrow_request("AU25UG100", "I002", 2)
    expect(ok, "Request creation failed")
    expect(app.transactions == {}, "Transaction should not exist before acceptance")
    ok, tx_id = app.accept_request("AU25UG045", req_id, date(2026, 9, 9))
    expect(ok and tx_id in app.transactions, "Accept failed")

    app2 = make_test_app()
    ok, req_id2 = app2.create_borrow_request("AU25UG100", "I002", 2)
    expect(ok, "Second request creation failed")
    ok, _ = app2.reject_request("AU25UG045", req_id2)
    expect(ok, "Reject failed")
    expect(app2.requests[req_id2].status == "REJECTED", "Request status should be REJECTED")
    expect(app2.items["I002"].status == "AVAILABLE", "Rejected item should be AVAILABLE")


def test_borrowing_activation():
    app, tx_id = setup_transaction(duration=4)
    tx = app.transactions[tx_id]
    expect(tx.status == "BORROWED", "Transaction not BORROWED")
    expect(app.items[tx.item_id].status == "BORROWED", "Item not BORROWED")
    expect(tx.due_date == date(2026, 9, 13), "Due date failed")
    expect(tx.daily_rent == 500 and tx.rental_amount == 2000, "Rental values failed")
    expect(tx.commission == 200 and tx.lender_earnings == 1800, "Commission/earnings failed")


def test_on_time_return_and_lender_connection():
    app, tx_id = setup_transaction(duration=3)
    ok, ret_id = app.return_item("AU25UG001", tx_id, "NO DAMAGE", date(2026, 9, 12))
    expect(ok, "Return failed")
    tx = app.transactions[tx_id]
    expect(tx.status == "RETURN_PENDING", "Return should be pending")
    expect(tx.late_fee == 0 and tx.damage_charge == 0, "On-time charges should be zero")
    record = app.returns[ret_id]
    expect(record.lender_id == "AU25UG045", "Return lender link failed")
    expect(record.return_condition == "NO DAMAGE", "Return condition failed")
    ok, _ = app.confirm_return("AU25UG045", ret_id)
    expect(ok and tx.status == "COMPLETED", "Lender confirmation failed")
    expect(app.items[tx.item_id].status == "AVAILABLE", "Item should be AVAILABLE")


def test_late_return_fee():
    expect(calculate_late_fee(500, 2) == 200, "Direct late-fee calculation failed")
    app, tx_id = setup_transaction(duration=1)
    ok, ret_id = app.return_item("AU25UG001", tx_id, "NO DAMAGE", date(2026, 9, 12))
    expect(ok, "Late return failed")
    tx = app.transactions[tx_id]
    expect(tx.late_days == 2, "Late day count failed")
    expect(tx.late_fee == 200, "Late fee should be ₹200 for ₹500 rental and 2 late days")
    ok, _ = app.confirm_return("AU25UG045", ret_id)
    expect(ok, "Late return confirmation failed")


def test_damage_charges():
    expected = {
        "NO DAMAGE": 0,
        "MINOR": 225,
        "MODERATE": 825,
        "SEVERE": 1350,
    }
    for condition, amount in expected.items():
        expect(calculate_damage_charge(1500, condition) == amount, f"Damage rate failed for {condition}")
        app, tx_id = setup_transaction(price=500, duration=3)
        ok, _ = app.return_item("AU25UG001", tx_id, condition, date(2026, 9, 12))
        expect(ok, f"Return failed for {condition}")
        expect(app.transactions[tx_id].damage_charge == amount, f"Stored damage charge failed for {condition}")


def test_complete_damage_message_and_no_note():
    app, tx_id = setup_transaction()
    ok, message = app.return_item("AU25UG001", tx_id, "COMPLETE DAMAGE", date(2026, 9, 12))
    expected = "Consult the AU25UG045 lender for further consequences. Pay the full amount of the item to the lender."
    expect(ok and message == expected, "Complete-damage message is incorrect")
    tx = app.transactions[tx_id]
    expect(tx.damage_charge == 0, "Complete damage must not create an automatic charge")
    expect(tx.return_condition == "COMPLETE DAMAGE", "Complete damage condition not recorded")
    record = next(iter(app.returns.values()))
    expect(not hasattr(record, "note"), "Return note must not exist")
    ok, confirm_message = app.confirm_return("AU25UG045", record.return_id)
    expect(not ok and "outside the application" in confirm_message.lower(), "Complete damage should not enter settlement workflow")


def test_cancel_pending_and_booking_and_reject_completed():
    app = make_test_app()
    ok, request_id = app.create_borrow_request("AU25UG100", "I002", 2)
    expect(ok, "Pending request creation failed")
    ok, _ = app.cancel_request_or_booking("AU25UG100", request_id)
    expect(ok, "Pending request cancellation failed")
    expect(app.items["I002"].status == "AVAILABLE", "Cancelled request should reopen item")

    app, tx_id = setup_transaction(duration=2)
    ok, _ = app.cancel_request_or_booking("AU25UG001", tx_id)
    expect(ok and app.transactions[tx_id].status == "CANCELLED", "Accepted booking cancellation failed")
    expect(app.items["I001"].status == "AVAILABLE", "Cancelled booking should reopen item")

    app, tx_id = setup_transaction()
    ok, ret_id = app.return_item("AU25UG001", tx_id, "NO DAMAGE", date(2026, 9, 12))
    expect(ok, "Return prerequisite failed")
    ok, _ = app.confirm_return("AU25UG045", ret_id)
    expect(ok, "Completion prerequisite failed")
    ok, message = app.cancel_request_or_booking("AU25UG001", tx_id)
    expect(not ok and "cancellable" in message.lower(), "Completed transaction should not be cancellable")


def test_empty_history():
    app = BorrowInsteadOfBuyApp(today=date(2026, 9, 9))
    expect(app.get_borrowing_history("AU25UG100") == [], "Empty history should be safe")
    expect(app.search_items() == [], "Empty item list should be safe")


def test_no_extra_features():
    app = BorrowInsteadOfBuyApp(today=date(2026, 9, 9))
    expect(not hasattr(app, "ratings"), "Ratings should not exist")
    item = next(iter(app.items.values()), None)
    expect(item is None, "Fresh application should not seed items")


TESTS = [
    test_student_id_validation_group,
    test_unknown_student_id,
    test_item_id_is_generated_and_unique,
    test_item_and_price_validation,
    test_input_parsers,
    test_rental_calculation,
    test_borrow_request_duration_and_unavailable_item,
    test_lender_accept_or_reject_request,
    test_borrowing_activation,
    test_on_time_return_and_lender_connection,
    test_late_return_fee,
    test_damage_charges,
    test_complete_damage_message_and_no_note,
    test_cancel_pending_and_booking_and_reject_completed,
    test_empty_history,
    test_no_extra_features,
]


if __name__ == "__main__":
    passed = 0
    failures = []
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
            passed += 1
        except AssertionError as exc:
            failures.append((test.__name__, str(exc)))
            print(f"FAIL {test.__name__}: {exc}")
        except Exception as exc:
            failures.append((test.__name__, f"Unexpected error: {exc}"))
            print(f"ERROR {test.__name__}: {exc}")

    print(f"\n{passed}/{len(TESTS)} tests passed.")
    if failures:
        print("\nFailures:")
        for name, message in failures:
            print(f"- {name}: {message}")
        raise SystemExit(1)
