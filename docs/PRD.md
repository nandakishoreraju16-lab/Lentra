# LENTRA
### Student-to-Student Resource Lending & Borrowing Management System
**PRODUCT REQUIREMENTS & FUNCTIONAL SPECIFICATION DOCUMENT (UPDATED v2.1)**  
*College Project • Python Terminal Application & Relational DBMS Integration*  

---

## 1. PROBLEM STATEMENT

Students often need items such as calculators, cameras, books, tools, projectors, sports equipment, and electronic accessories for only a short period. Buying an item for temporary use can create unnecessary expense, while other students may already own useful items that are not being used.

**LENTRA** (*"Borrow Instead of Buy"*) is a Python terminal application that connects students who need an item temporarily with students willing to lend items they already own. The system lets lenders list items, borrowers browse a simple available-item list and request an item, lenders accept or reject the request, and the application tracks borrowing, returns, late fees, damage charges, cancellations, earnings, and transaction history.

### Enhancements Included in this Updated Release:
1. **Relational DBMS Persistence (SQLite):** Replaced volatile in-memory storage with an ACID-compliant SQLite database (`borrow_app.db`) using ANSI SQL foreign key constraints to ensure complete durability across terminal restarts.
2. **Account Safety & Trust Policy (4-Digit PIN):** Added personal 4-digit security PIN setup on first login and validation on subsequent logins to protect student accounts against unauthorized peer tampering.
3. **Shorthand Roll Number Input:** Students can log in using either their full ID (`AU25UG028`) or convenient shorthand roll numbers (`28`), which are automatically normalized.
4. **Streamlined Batch Approval & Settlement:** Lenders can batch-approve all waiting requests and confirm settlements in 1 click.
5. **Lender Notification Badging:** Implemented real-time home-screen alert banners (`🔔 NOTIFICATIONS`) to notify lenders of pending requests and returns awaiting confirmation.
6. **Master Campus Resource & Audit Dashboard:** Added an administrative oversight dashboard unlocked via a case-insensitive secret passkey (`nandu1216@#$` autocorrected to uppercase `NANDU1216@#$`), allowing evaluators and campus admins to audit who the lender is, what item they listed, who borrowed it, and whether it has been returned or not (`[NOT RETURNED]` vs `[RETURNED]`).

---

## 2. INTERFACE SPECIFICATION

### INPUTS

| Input | Baseline PRD Requirement | Updated / Extended Behavior |
| :--- | :--- | :--- |
| **Student ID / Roll Number** | Required for access. Must be `AU25UG001`–`AU25UG100`. Lowercase input is converted to uppercase before validation. | Accepts full ID (`AU25UG028`) or numeric shorthand roll numbers (`1` to `100`), auto-normalized with zero-padding. |
| **Security PIN** *(New)* | *Not present in baseline PRD.* | 4-digit numeric code entered by the student upon first login; required for verification on all subsequent sessions. |
| **Master Admin Passkey** *(New)* | *Not present in baseline PRD.* | Secret passkey entered via Option `3. Admin` or as direct menu shortcut (`nandu1216@#$`, `Nandu1216@#$`, `NANDU1216@#$`). Automatically converts/autocorrects to uppercase `NANDU1216@#$` and grants entry to the Master Relational Audit Dashboard. |
| **Item ID** | Unique identifier entered by the lender. | System auto-generates or verifies unique sequential identifiers (`I001`, `I002`, ...). |
| **Item Name** | Name of the item offered for lending. | Non-empty string trimmed of whitespace. |
| **Item Condition** | Condition entered by the lender when the item is listed. | Text description (e.g., `New`, `Good`, `Fair`). |
| **Rental Price per Day** | Positive numeric rental price in Indian Rupees (₹). | Enforces numeric value $> 0.00$. |
| **Borrowing Duration** | Positive whole-number duration in days. | Enforces integer $> 0$. |
| **Item Selection** | Item number selected from the borrower’s simple available-item list. | Validated against listed index numbers. |
| **Borrow Request Decision** | Lender chooses Accept or Reject for a pending request shown within the relevant listed item. | Lenders can Accept/Reject, or use 1-click batch approval. |
| **Return Condition** | One of: `No Damage`, `Minor Damage`, `Moderate Damage`, `Severe Damage`, `Complete Damage`. | Strict enum validation against the 5 standardized condition tiers. |
| **Cancellation Choice** | Selection of an eligible pending request or accepted booking to cancel. | Selects transaction by ID; verifies that status is cancellable (cannot cancel completed returns). |

### OUTPUTS

| Output | Baseline PRD Behavior | Updated / Extended Behavior |
| :--- | :--- | :--- |
| **Verification & Security** | Student verified, or a clear validation error while remaining on the current Student ID prompt. | Prompts for 4-digit PIN setup for new users or PIN authentication for returning users with attempt tracking. |
| **Available Item List** | A clean numbered list showing Item ID, item name, condition, rental price per day, and lender ID. | Clean formatted table with status filtering; excludes the borrower's own listed items. |
| **My Listed Items** | The lender’s items with their current status plus relevant pending request or return activity inside the same item view. | Status view showing items (`AVAILABLE`, `REQUESTED`, `BORROWED`) and nested pending borrow/return requests. |
| **Notification Alert** *(New)* | *Not present in baseline PRD.* | Visual banner on lender dashboard displaying counts of pending requests and returns (`🔔 NOTIFICATIONS`). |
| **Master Audit Dashboard** *(New)* | *Not present in baseline PRD.* | Comprehensive administrative matrix displaying: (1) Lender ID and name, (2) Item details and daily rent, (3) Borrower ID and name, (4) Return status (`[NOT RETURNED]` with due date / overdue tracking vs `[RETURNED]` with settlement breakdown). |
| **Request Status** | `Pending`, `Accepted`, `Rejected`, or `Cancelled`. | Preserved exact status transitions in both memory and SQLite tables. |
| **Borrowing Details** | Duration, daily price, rental amount, 10% commission, 90% lender earnings, start date, and due date. | Formatted breakdown showing complete financial calculations in Indian Rupees (₹). |
| **Return / Charge Details** | Return condition, return date, late days, late fee, and applicable damage charge. | Comprehensive itemized return receipt showing base rent, late penalties, damage fees, and total due. |
| **Earnings and History** | Lender earnings, commission deductions, and borrowing/lending transaction history. | Detailed ledger showing all past borrowings, lendings, cancellations, and net lender earnings. |
| **Complete-Damage Message** | *“Consult the AU25UGXXX lender for further consequences. Pay the full amount of the item to the lender.”* | Dynamic substitution of actual lender ID. Workflow terminates immediately with zero automated charge. |
| **Persistence Status** *(New)* | *Not present in baseline PRD.* | Status banner confirming connection to persistent relational SQLite database (`borrow_app.db`). |

---

## 3. FUNCTIONAL REQUIREMENTS

| ID | Grouped Requirement | Details & Business Rules | Status |
| :---: | :--- | :--- | :---: |
| **FR1** | **Student Access, ID Validation & Shorthand** | Accept a Student ID, convert lowercase to uppercase, validate the fixed `AU25UG` prefix and `001–100` range, verify that the student exists in the cohort, and keep prompting after invalid input without crashing. **Added:** Supports shorthand roll numbers (`1`–`100`) auto-expanded to `AU25UG001`–`AU25UG100`. | **Enhanced** |
| **FR2** | **Item Listing & My Listed Items** | A lender can add an item using Item ID, Item Name, Condition, and Rental Price per Day. Item IDs must be unique. New items start as `AVAILABLE`. All relevant request/return activity is shown from My Listed Items. | **Baseline** |
| **FR3** | **Browse, Request & Decide** | A borrower sees a simple numbered list of available items, selects an item and duration (days $> 0$), and creates a `PENDING` request. The lender can `ACCEPT` or `REJECT` the request from the relevant listed item. | **Baseline** |
| **FR4** | **Borrowing, Return, Late Fee & Damage** | Accepted requests become `BORROWED` and store the rental period, financial values, start date, and due date. A borrower can return the item. Late returns add 20% of the original rental fee per late day. Damage charges use the finalized damage rules below. | **Baseline** |
| **FR5** | **Cancellation** | A borrower can cancel a pending request, and a lender can cancel an accepted booking while cancellable. Once cancelled, the item resets cleanly to `AVAILABLE`. Completed/returned transactions cannot be cancelled. | **Baseline** |
| **FR6** | **Charges, Earnings & History** | Show rental amount, 10% platform commission, 90% lender earnings, applicable late/damage charges, and borrowing/lending history. This is an academic simulation; no real monetary payment is processed. | **Baseline** |
| **FR7** | **Account Safety & 4-Digit Security PIN** | *(New Requirement)* Protect student accounts against unauthorized peer impersonation. On first login, prompt the user to register a 4-digit PIN. On subsequent logins, require PIN verification. Deny login after 3 consecutive failed attempts. | **New** |
| **FR8** | **Quick Batch Approval & Settlement** | *(New Requirement)* Provide lenders with a **1-Click Batch Approval** (`0. ⚡ Approve All`) option to streamline peer reviews. | **New** |
| **FR9** | **Relational DBMS Persistence & ACID Integrity** | *(New Requirement)* Store all students, items, requests, transactions, return records, and cancellation events persistently in SQLite (`borrow_app.db`). Enforce relational integrity with foreign keys (`ON DELETE RESTRICT`) so all records survive terminal restarts. | **New** |
| **FR10** | **Master Campus Resource & Audit Dashboard** | *(New Requirement)* Administrative oversight interface protected by a password gate. Main menu offers `3. Admin`, prompting for password `NANDU1216@#$` (with case-insensitive autocorrect from `nandu1216@#$`). Directly typing the passkey at the main menu also functions as a shortcut. The dashboard renders an eye-catching, colorful visual layout displaying: (1) Colored KPI metrics banner, (2) **Section 1: Lender Asset List** with [1st] Lender ID, [2nd] Lender Name, items, condition, cost per day, and colored status pills, (3) **Section 2: Borrower Loans** specifying who borrowed what from a particular lender AU_ID and for how many days, with real-time return status (`🔴 [NOT RETURNED]` vs `🟡 [RETURN PEND]` vs `🟢 [RETURNED]`), and (4) Bottom actions to filter by Lender AU_ID, inspect detailed ledger cards, or view DBMS diagnostics. | **New** |

---

## 4. DAMAGE RULES

| Return Condition | Additional Charge | Terminal Behavior |
| :--- | :---: | :--- |
| **No Damage** | 0% of rental price | Normal return flow; no additional penalty applied. |
| **Minor Damage** | 15% of rental price | Apply 15% surcharge ($\text{Rental} \times 0.15$) and record the condition. |
| **Moderate Damage** | 55% of rental price | Apply 55% surcharge ($\text{Rental} \times 0.55$) and record the condition. |
| **Severe Damage** | 90% of rental price | Apply 90% surcharge ($\text{Rental} \times 0.90$) and record the condition. |
| **Complete Damage** | No percentage calculation | Show the lender-specific message, record the condition, and end the workflow. Do not ask for a note or start any negotiation/settlement process. |

### COMPLETE DAMAGE MESSAGE CALLOUT
> **“Consult the AU25UGXXX lender for further consequences. Pay the full amount of the item to the lender.”**  
> *(AU25UGXXX is replaced by the actual lender Student ID. The application does not handle the consequence, negotiation, or payment).*

---

## 5. EDGE CASES

| ID | Grouped Edge Case | Expected Handling |
| :---: | :--- | :--- |
| **EC1** | **Student ID Validation** | Reject blank, malformed, numeric-only out-of-range, wrong-prefix, wrong-length, `AU25UG000`, `AU25UG101`, and unknown IDs. Normalize lowercase input first and keep prompting on the same verification screen. Accept valid shorthand (`1`–`100`). |
| **EC2** | **Duplicate Records & Invalid Item Data** | Do not create duplicate student records. Reject duplicate Item IDs, zero, negative, or non-numeric rental prices, and invalid/empty item names. |
| **EC3** | **Borrowing Request State & Self-Borrowing** | Do not request unavailable items. Prevent students from requesting their own listed items. Only pending requests can be accepted or rejected. Rejected requests end cleanly and do not permanently block the item. |
| **EC4** | **Duration & Late Return** | Reject zero, negative, or non-numeric duration. When returned after the due date, calculate exact late days and charge exactly 20% of the original rental fee per late day overdue ($\text{Rental} \times 0.20 \times \text{Late Days}$). |
| **EC5** | **Return Condition & Complete Damage** | Reject unsupported return conditions. For Complete Damage, display the lender-specific message, request no note, record the condition, and terminate the return workflow. |
| **EC6** | **Cancellation State** | Do not allow cancellation of completed or returned transactions. Cancelled requests and bookings must not remain active or permanently block the item from future borrowing. |
| **EC7** | **Empty States & Menu Errors** | Show clear, informative messages for no available items or empty borrowing/lending history. Invalid menu choices must display an error and keep the user in the current menu context without crashing. |
| **EC8** | **Security PIN Validation & Lockout** *(New)* | Reject PINs that are not exactly 4 numeric digits. For returning students, prompt for PIN and reject mismatched inputs. Deny access after 3 consecutive failed attempts. |
| **EC9** | **DBMS Foreign Key & Concurrency Integrity** *(New)* | Disallow inserting items or transactions referencing non-existent students at the database level (`FOREIGN KEY ... ON DELETE RESTRICT`). Ensure that completely closing and restarting the process reloads all records intact. |
| **EC10** | **Admin Menu & Password Gate** *(New)* | The main menu presents (1. Lender, 2. Borrower, 3. Admin, 4. Exit). Choosing `3` prompts for Admin Password. Entering `nandu1216@#$` in lowercase, uppercase, or mixed case is automatically autocorrected to uppercase `NANDU1216@#$` and unlocks the dashboard. Directly entering the passkey at the main menu choice also grants access. Unrecognized menu options safely reject with `"Invalid menu choice. Choose 1 to 4."` |


---

## 6. TEST CASES & VERIFICATION MATRIX

| ID | Test Area | Test Action | Expected Result | Status |
| :---: | :--- | :--- | :--- | :---: |
| **TC01** | **Student ID Validation** | Test blank, malformed, `AU25UG000`, `AU25UG101`, numeric-only, unknown, and lowercase IDs (`au25ug001`). | Invalid IDs are rejected without leaving the verification screen; valid lowercase input is normalized and accepted. | **PASS** |
| **TC02** | **Item and Price Validation** | Add an item, test duplicate Item ID, and test zero, negative, and text rental prices. | Valid item is created as `AVAILABLE`; duplicate Item IDs and invalid prices are rejected. | **PASS** |
| **TC03** | **Rental Calculation** | Test item at ₹500/day for 3 days. | Base Rental: **₹1,500**; Platform Commission (10%): **₹150**; Lender Earnings (90%): **₹1,350**. | **PASS** |
| **TC04** | **Borrow Request and Decision** | Request an available item, then accept and reject requests from My Listed Items. | Pending request is linked to borrower/lender/item; Accept activates borrowing; Reject ends request and leaves item usable. | **PASS** |
| **TC05** | **Borrowing Activation** | Accept a valid request with start date and duration. | Duration, daily price, rental amount, commission, lender earnings, start date, and due date are recorded; item becomes `BORROWED`. | **PASS** |
| **TC06** | **Invalid Duration / Unavailable Item** | Use 0, negative, text duration, or try to request a non-available item. | Input is rejected with clear error; request is blocked. | **PASS** |
| **TC07** | **On-Time Return** | Return on or before due date with condition `No Damage`. | Return is recorded (late fee = ₹0, damage = ₹0), and item becomes `AVAILABLE` after normal completion. | **PASS** |
| **TC08** | **Late Return Fee** | Return 2 days late on a ₹500 rental fee. | Late fee = **₹200** ($20\% \times \text{₹}500 \times 2$ days). | **PASS** |
| **TC09** | **Damage Charges** | Test Minor, Moderate, and Severe damage on ₹1,500 rental. | Apply 15% (₹225), 55% (₹825), and 90% (₹1,350) respectively and record condition in transaction ledger. | **PASS** |
| **TC10** | **Complete Damage** | Select Complete Damage on return. | Show exact lender-specific message (`AU25UGXXX`), request no note, record condition, and end workflow with ₹0 auto charge. | **PASS** |
| **TC11** | **Cancellation** | Cancel a pending request or cancellable booking; attempt to cancel a completed transaction. | Eligible cancellation succeeds and resets item to `AVAILABLE`; completed transaction cancellation is rejected. | **PASS** |
| **TC12** | **Charges, History & Menu Behavior** | View earnings/history; test empty history, no available items, and invalid menu choices. | Correct information or clear empty/error messages are shown; user remains in current menu. | **PASS** |
| **TC13** | **Roll Number Shorthand Normalization** *(New)* | Enter numeric shorthand `1`, `28`, `100` at login prompt. | System automatically expands and normalizes inputs to `AU25UG001`, `AU25UG028`, `AU25UG100`. | **PASS** |
| **TC14** | **Security PIN Authentication** *(New)* | Test first-time 4-digit PIN setup (`1234`), login with correct PIN, login with wrong PIN, and 3-attempt lockout. | Enforces 4-digit numeric format; verifies against stored record; locks account after 3 failures. | **PASS** |
| **TC15** | **Batch Approval Flow** *(New)* | Lender uses 1-click batch approval (`0. ⚡ Approve All`). | Automatically approves all pending requests and transitions items to `BORROWED`. | **PASS** |
| **TC16** | **DBMS Multi-Session Persistence** *(New)* | Create items and transactions in Session 1; exit application; start new Session 2 from SQLite. | Complete database state reloads identically; all items, bookings, PINs, and histories are preserved. | **PASS** |
| **TC17** | **Relational Foreign Key Integrity** *(New)* | Attempt inserting an item or request referencing non-existent student directly into SQLite. | Database engine enforces `PRAGMA foreign_keys = ON` and aborts transaction with `IntegrityError`. | **PASS** |
| **TC18** | **Master Dashboard Audit & Passkey Autocorrect** *(New)* | Enter passkey permutations (`nandu1216@#$`, `Nandu1216@#$`, `NANDU1216@#$`). Verify uppercase autocorrect. Verify ledger correctly marks active borrowings as `[NOT RETURNED]` and completed transactions as `[RETURNED]`. | All case permutations autocorrect to `NANDU1216@#$` and grant access. Ledger precisely tracks lender, item, borrower, and return status. | **PASS** |

---

## 7. SUMMARY OF ENHANCEMENTS ("WHAT WE INCLUDED NOW")

The following table summarizes the evolution from the baseline PRD to the current implementation:

| Functional Area | Baseline PRD (v1.1) | Current Implementation (v2.1) | Rationale & User Impact |
| :--- | :--- | :--- | :--- |
| **Data Storage** | Volatile Python in-memory dictionaries & lists. | Persistent, ACID-compliant **SQLite relational DBMS** (`borrow_app.db`). | Prevents total data loss upon terminal exit; satisfies academic DBMS requirements with relational tables, foreign keys, and indexes. |
| **Student Login** | Full 9-character ID required (`AU25UG001`–`AU25UG100`). | Full ID or **shorthand roll numbers** (`1`–`100`) auto-normalized to 9-char format. | Minimizes repetitive typing when testing or switching between peer accounts. |
| **Account Security** | Unrestricted access upon typing any valid Student ID. | **4-digit personal Security PIN** required for all accounts. | Implements practical peer security policy; prevents malicious students from impersonating classmates. |
| **Borrowing Approval** | Strict two-step process: Borrower requests $\rightarrow$ log out $\rightarrow$ log in as Lender to accept. | **Batch review mode:** Standard review with **1-Click Batch Approval** (`0. ⚡ Approve All`). | Streamlines approval workflow without bypassing lender authorization. |
| **Lender Dashboard** | Passive list of items with nested activity. | Active **Notification Alert Banner** (`🔔 NOTIFICATIONS`) on home screen + 1-Click approval. | Immediate visibility into pending borrower requests and item return requests. |
| **Return Settlement** | Return recorded only from borrower's flow. | Borrower return with optional **Instant Settlement** or lender-side confirmation. | Streamlined returns while preserving deterministic late-fee and damage calculations. |
| **Administrative Audit Dashboard** | *Not present in baseline PRD.* | **Master Campus Audit Dashboard** unlocked via case-insensitive passkey `NANDU1216@#$` (autocorrected from lowercase/mixed-case). | Enables evaluators and administrators to audit all lenders, items, borrowers, and return statuses (`[NOT RETURNED]` vs `[RETURNED]`) at a glance without switching accounts. |

> [!NOTE]
> **Scope Confirmation regarding Physical OTP (Layer 2):**  
> In accordance with academic project scope guidelines, complex physical handover verification mechanisms (such as SMS/Email two-factor OTP handshakes) were intentionally omitted. The project focuses on clean software architecture, relational data modeling, and intuitive terminal UX.
