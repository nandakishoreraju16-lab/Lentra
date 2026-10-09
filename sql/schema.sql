-- ============================================================
-- "Borrow Instead of Buy" - Relational Database Schema
-- Database Engine: SQLite 3 / ANSI SQL Compatible
-- ============================================================

PRAGMA foreign_keys = ON;

-- 1. STUDENTS TABLE
CREATE TABLE IF NOT EXISTS students (
    student_id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    pin VARCHAR(10) NOT NULL DEFAULT ''
);

-- 2. ITEMS TABLE
CREATE TABLE IF NOT EXISTS items (
    item_id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    condition VARCHAR(50) NOT NULL,
    rental_price_per_day REAL NOT NULL CHECK(rental_price_per_day > 0),
    lender_id VARCHAR(10) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE' CHECK(status IN ('AVAILABLE', 'REQUESTED', 'BORROWED')),
    FOREIGN KEY (lender_id) REFERENCES students(student_id) ON DELETE RESTRICT
);

-- 3. BORROW REQUESTS TABLE
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

-- 4. TRANSACTIONS TABLE
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

-- 5. RETURN RECORDS TABLE
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

-- 6. CANCELLATIONS TABLE
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

-- 7. AUDIT HISTORY LOG TABLE
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

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_items_lender ON items(lender_id);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_requests_item ON borrow_requests(item_id);
CREATE INDEX IF NOT EXISTS idx_requests_borrower ON borrow_requests(borrower_id);
CREATE INDEX IF NOT EXISTS idx_requests_status ON borrow_requests(status);
CREATE INDEX IF NOT EXISTS idx_transactions_borrower ON transactions(borrower_id);
CREATE INDEX IF NOT EXISTS idx_transactions_lender ON transactions(lender_id);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
