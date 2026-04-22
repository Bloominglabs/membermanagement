# Membership Manager — Development Plan & Handoff Document

Historical prototype document. This file describes the earlier Google Sheets and PayPal direction and is retained only for reference; it is not authoritative for the current Django/Postgres system.

**Version:** 2.1 (handoff)  
**Date:** February 23, 2026  
**Platform:** Google Sheets + Google Apps Script + PayPal Invoicing API v2  
**Architecture:** Google Sheets is the sole data store and single source of truth. No external database. All data must remain in plain text within sheets, exportable and backupable.

---

## 1. Project Context

A non-profit organization is replacing Freshbooks with a custom, zero-cost membership management and invoicing system built entirely within Google Sheets. The system uses Google Apps Script for automation and the PayPal Invoicing API for payment processing. PayPal is treated as a downstream payment processor — the Sheet drives PayPal, not the other way around.

### Design Principles

1. **Google Sheets is the single source of truth.** Every piece of organizational data lives in a sheet. PayPal is queried for payment status, but the Sheet is authoritative.
2. **Plain text everything.** All data must be stored as plain values in cells (no hidden metadata, no JSON blobs). If the system ever migrates to a database, a CSV export of every sheet must be sufficient.
3. **Regular automated backups** to a separate, read-only spreadsheet.
4. **Menu-driven UI.** All actions are triggered from the `💼 Membership Manager` custom menu. No coding knowledge required for day-to-day operation.
5. **Idempotent operations.** Monthly invoicing checks for duplicates. Payment status checks are safe to re-run. Migrations detect current state before acting.

### PayPal Integration Notes

- **API:** PayPal Invoicing API v2 (`/v2/invoicing/invoices`)
- **Auth:** OAuth2 client credentials flow via `UrlFetchApp`
- **Invoicer email:** Must match the sandbox/live business account email associated with the REST API app in the PayPal Developer Dashboard. This is a common source of `USER_NOT_FOUND` errors.
- **Sandbox credential propagation:** New credentials can take several minutes to become active. The test connection function may fail immediately after creation — wait and retry.
- **Rate limits:** ~30 API calls/minute. The code includes `Utilities.sleep(1000)` delays when processing batches > 5.
- **Payment tracking:** The script polls PayPal hourly (configurable) via `GET /v2/invoicing/invoices/{id}` and reads the `status` field. PayPal statuses mapped: PAID, MARKED_AS_PAID → "Paid"; CANCELLED → "Cancelled"; REFUNDED → "Refunded"; PARTIALLY_PAID → "Partial".

---

## 2. Current State — What Exists

### 2.1 Sheets

| Sheet | Purpose | Status |
|-------|---------|--------|
| **Config** | Organization info, PayPal credentials, rates, defaults | ✅ Working |
| **Members** | Member roster: ID, name, email, tier, status | ✅ Working (needs expansion — see §4) |
| **Invoices** | All invoices (dues + custom), 13 columns | ✅ Working |
| **Custom Invoices** | Staging area for ad-hoc invoices | ✅ Working |
| **Dashboard** | At-a-glance stats | ✅ Working (needs expansion — see §4) |

### 2.2 Invoices Sheet Column Layout (v2, current)

```
Col  Header              Type      Notes
───  ──────────────────  ────────  ─────────────────────────────────────
A    Invoice #           String    Format: MEM-YYYY-MM-NNN
B    Type                String    "Dues" or "Custom"
C    Member ID           String    Links to Members sheet (blank for non-members)
D    Recipient Name      String    "First Last"
E    Email               String    Recipient email
F    Description         String    Line item description
G    Amount              Number    USD, formatted $#,##0.00
H    Month/Year          String    "January 2026" format
I    Date Sent           Date      yyyy-mm-dd
J    Status              String    Sent | Paid | Cancelled | Refunded | Partial | Overdue
K    Date Paid           Date      yyyy-mm-dd (blank until paid)
L    PayPal Invoice ID   String    PayPal's internal ID (e.g. INV2-XXXX-XXXX-XXXX-XXXX)
M    PayPal Invoice URL  String    API href for the invoice resource
```

### 2.3 Functions — Inventory

**Menu/UI Functions (called by user):**

| Function | Description | Status |
|----------|-------------|--------|
| `onOpen()` | Creates the custom menu | ✅ |
| `initializeSheets()` | Creates/formats all sheets | ✅ Needs update for new sheets |
| `sendMonthlyInvoices()` | Interactive: sends dues invoices to all active members | ✅ Needs refactor for per-member rates |
| `sendInvoiceToSelected()` | Interactive: sends dues invoice to one member | ✅ Needs refactor for per-member rates |
| `sendCustomInvoices()` | Interactive: sends all unsent rows from Custom Invoices sheet | ✅ |
| `viewInvoicesForSelected()` | Dialog: shows invoices for selected member | ✅ |
| `searchInvoicesByRecipient()` | Dialog: searches invoices by name/email | ✅ |
| `checkPaymentStatus()` | Polls PayPal for payment updates | ✅ |
| `markSelectedPaid()` | Manual override: marks invoice paid | ✅ Needs PayPal sync (see §4) |
| `cancelSelectedInvoice()` | Cancels invoice in Sheet + PayPal | ✅ |
| `migrateInvoicesSheet()` | One-time v1→v2 column migration | ✅ (can be removed in next version) |
| `enableAutoCheck()` | Creates hourly payment check trigger | ✅ |
| `enableAutoInvoicing()` | Creates monthly invoicing trigger | ✅ |
| `removeAllTriggers()` | Removes all time-based triggers | ✅ |
| `testPayPalConnection()` | Verifies PayPal API credentials | ✅ |
| `refreshDashboard()` | Rebuilds dashboard stats | ✅ Needs update for new data |

**Internal Helper Functions (not directly called by user):**

| Function | Description |
|----------|-------------|
| `getConfig()` | Reads Config sheet into an object |
| `getActiveMembers()` | Returns array of active members |
| `formatMonthYear(date)` | "January 2026" format |
| `generateInvoiceNumber(config, date)` | Auto-incrementing invoice numbers |
| `getPayPalToken_(config)` | OAuth2 token exchange |
| `paypalRequest_(config, token, method, path, payload)` | Generic PayPal API caller with error handling |
| `buildInvoicePayload_(config, recipient, invoiceNum, items, opts)` | Constructs PayPal invoice JSON |
| `createAndSendInvoice_(config, token, recipient, invoiceNum, items, opts)` | Creates draft + sends via PayPal |
| `buildDuesItems_(tier, monthYear, amount, config)` | Builds line items for membership dues |
| `logInvoice_(invoicesSheet, ...)` | Appends a row to the Invoices sheet |
| `getAllInvoices_()` | Returns all invoices as objects |
| `showInvoiceDialog_(title, invoices)` | Renders HTML dialog with invoice table |
| `autoSendMonthlyInvoices()` | Trigger-compatible (no UI) version of sendMonthlyInvoices |

---

## 3. Current Code

The full, current codebase is included as the companion file `MembershipManager_v2.gs`. It is approximately 1,500 lines of Google Apps Script (JavaScript). The code sections, in order:

1. **CONFIGURATION** (lines 1–29): Default values and PayPal endpoint URLs.
2. **MENU** (lines 33–57): `onOpen()` builds the custom menu.
3. **SHEET SETUP** (lines 59–210): `initializeSheets()` creates and formats all sheets.
4. **CONFIG HELPERS** (lines 212–285): `getConfig()`, `getActiveMembers()`, `formatMonthYear()`, `generateInvoiceNumber()`.
5. **PAYPAL API** (lines 287–354): `getPayPalToken_()`, `paypalRequest_()` — the low-level API layer.
6. **INVOICE CREATION** (lines 356–483): `buildInvoicePayload_()`, `createAndSendInvoice_()`, `buildDuesItems_()`, `logInvoice_()`.
7. **SEND INVOICES** (lines 485–648): `sendMonthlyInvoices()`, `sendInvoiceToSelected()`.
8. **CUSTOM INVOICES** (lines 650–770): `sendCustomInvoices()`.
9. **INVOICE LOOKUP** (lines 772–941): `getAllInvoices_()`, `showInvoiceDialog_()`, `viewInvoicesForSelected()`, `searchInvoicesByRecipient()`.
10. **DATA MIGRATION** (lines 943–1072): `migrateInvoicesSheet()` — one-time v1→v2.
11. **PAYMENT STATUS** (lines 1074–1188): `checkPaymentStatus()`.
12. **CANCEL INVOICE** (lines 1190–1260): `cancelSelectedInvoice()`.
13. **MARK PAID** (lines 1262–1282): `markSelectedPaid()`.
14. **TRIGGERS** (lines 1284–1379): `enableAutoCheck()`, `enableAutoInvoicing()`, `autoSendMonthlyInvoices()`, `removeAllTriggers()`.
15. **TEST CONNECTION** (lines 1381–1408): `testPayPalConnection()`.
16. **DASHBOARD** (lines 1410–1507): `refreshDashboard()`.

---

## 4. Feature Roadmap

### Phase 1: Member Data Model Expansion

**Goal:** The Members sheet becomes a full membership record with per-member dues, address, and join/leave tracking.

#### 4.1 Expand the Members Sheet

Current columns:
```
Member ID | First Name | Last Name | Email | Tier | Status | Date Added | Notes
```

New columns (append to the right of existing data to preserve existing rows):
```
Member ID | First Name | Last Name | Email | Address Line 1 | Address Line 2 | City | State | Postal Code | Country | Phone | Tier | Status | Monthly Dues Override | Date Joined | Date Left | Notes
```

Key changes:
- **Address fields** (Line 1, Line 2, City, State, Postal Code, Country) — needed for formal correspondence and may be referenced by 3rd party tools.
- **Phone** — optional contact info.
- **Tier** — rename values from "Full"/"Half" to "Full"/"Hardship" throughout. Update all dropdown validations.
- **Status** — expand from ["Active", "Paused"] to ["Active", "Paused", "Left"]. "Left" means the member has departed the organization.
- **Monthly Dues Override** — a number. If blank or 0, the system uses the tier default from Config. If populated (e.g., 40), that member is billed this amount instead. This supports legacy rates and individual arrangements.
- **Date Joined** — replaces "Date Added". Tracks when the member joined (or rejoined).
- **Date Left** — populated when status changes to "Left". Blank for active/paused members.

#### 4.2 Audit Log Sheet (NEW)

Create a new sheet called **"Audit Log"** that records every state change to a member. This is append-only and never edited.

```
Timestamp | Member ID | Member Name | Field Changed | Old Value | New Value | Changed By
```

Examples:
```
2026-02-23 14:30 | M001 | Jane Smith | Status       | Active | Paused   | admin@org.com
2026-02-23 14:30 | M001 | Jane Smith | Tier         | Full   | Hardship | admin@org.com
2026-03-01 09:00 | M005 | Bob Lee    | Monthly Dues | 50.00  | 40.00    | admin@org.com
```

**Implementation approach:** Use an `onEdit()` trigger that watches the Members sheet. When a cell in certain columns (Tier, Status, Monthly Dues Override) changes, append a row to the Audit Log. The `onEdit(e)` simple trigger receives the edit event with old and new values via `e.oldValue` (note: `onEdit` only provides `oldValue` for single-cell edits — not range pastes. Document this limitation).

For changes made programmatically (e.g., a future "Pause Member" menu action), the code should call a shared `logAuditEntry_(memberId, memberName, field, oldVal, newVal)` function.

#### 4.3 Update `getActiveMembers()` and Dues Logic

Currently, `sendMonthlyInvoices` reads the tier and uses `config.FULL_RATE` or `config.HALF_RATE`. Refactor to:

```javascript
function getMemberDuesAmount_(member, config) {
  // Per-member override takes precedence
  if (member.duesOverride && member.duesOverride > 0) {
    return member.duesOverride;
  }
  // Fall back to tier default
  if (member.tier === "Full") return config.FULL_RATE;
  if (member.tier === "Hardship") return config.HALF_RATE;
  return config.FULL_RATE; // safety fallback
}
```

Update `getActiveMembers()` to read the new columns and include `duesOverride` in the returned objects.

#### 4.4 Config Sheet Updates

Add rows:
- **Hardship Rate ($)** — rename from "Half Rate ($)" for clarity.
- **Organization Email** — the org's primary email, used as reply-to and for overdue notices.
- **Overdue Notice Default (days)** — default number of days after due date before an overdue notice is sent. Default: 14.
- **Backup Spreadsheet ID** — the Google Sheets ID of the backup spreadsheet (see §Phase 5).

#### 4.5 Migration Function

Write `migrateMembers_v2_to_v3()` that:
1. Backs up the Members sheet.
2. Inserts the new columns at the correct positions.
3. Copies "Date Added" values into "Date Joined".
4. Renames "Half" tier values to "Hardship".
5. Leaves Monthly Dues Override blank for all existing members (they continue using tier defaults).

**Test guidance:** Before running on real data, create a test sheet with 5 rows of sample member data. After migration, verify: (a) all original data is preserved in the correct columns, (b) new columns exist with correct headers, (c) "Half" → "Hardship" rename applied, (d) Date Joined populated from Date Added, (e) backup sheet created.

---

### Phase 2: Recurring Invoices Engine

**Goal:** Replace the current "monthly dues only" auto-invoicing with a general-purpose recurring invoices system that handles any recurring charge — member dues, vendor fees, quarterly assessments, etc.

#### 4.6 Recurring Invoices Sheet (NEW)

Create a new sheet called **"Recurring Invoices"** that defines recurring billing schedules.

```
Schedule ID | Recipient Type | Recipient ID/Email | First Name | Last Name | Email | Description | Amount | Frequency | Day of Month (Send) | Day of Month (Due) | Start Date | End Date | Overdue Notice (days) | Active | Last Sent | Notes
```

Column details:
- **Schedule ID** — unique identifier, e.g., "R001".
- **Recipient Type** — "Member" or "External". If "Member", the Recipient ID/Email column holds a Member ID; the system looks up the current email from the Members sheet (so if a member updates their email, the recurring invoice goes to the new address).
- **Recipient ID/Email** — Member ID (if Member) or email address (if External).
- **First Name / Last Name / Email** — for External recipients, filled in directly. For Members, auto-populated at send time from the Members sheet.
- **Description** — the line item description (e.g., "Full Membership Dues", "Quarterly Vendor Fee").
- **Amount** — the charge amount. For member dues, this can be blank/0 to mean "use the member's current dues amount" (from their override or tier default).
- **Frequency** — dropdown: "Monthly", "Quarterly", "Annually".
- **Day of Month (Send)** — day the invoice is created and sent. Default: 1.
- **Day of Month (Due)** — day the invoice is due. Default: 15.
- **Start Date / End Date** — the window during which this schedule is active. End Date blank means indefinite.
- **Overdue Notice (days)** — override for how long after the due date to send an overdue notice. Blank = use Config default.
- **Active** — "Yes" or "No" dropdown.
- **Last Sent** — auto-populated with the date the schedule was last triggered. Used to prevent double-sends.

#### 4.7 Auto-Populate Recurring Invoices for Existing Members

Write a function `generateDuesSchedules()` that, for every Active member in the Members sheet, creates a row in the Recurring Invoices sheet with:
- Recipient Type = "Member"
- Recipient ID = their Member ID
- Description = "[Tier] Membership Dues"
- Amount = 0 (meaning "use member's current rate")
- Frequency = "Monthly"
- Day of Month (Send) = 1
- Day of Month (Due) = 15
- Active = "Yes"

This replaces the current `sendMonthlyInvoices()` / `autoSendMonthlyInvoices()` functions, which hard-code the member iteration logic.

#### 4.8 Recurring Invoice Processor

Write `processRecurringInvoices()` — the new heart of the automation:

```
For each row in Recurring Invoices where Active = "Yes":
  1. Check if the schedule should fire today (based on Frequency + Day of Month + Last Sent).
  2. Check that Start Date <= today <= End Date (if End Date set).
  3. Resolve the recipient:
     - If Member: look up current name, email from Members sheet. Skip if member is Paused or Left.
     - If External: use the row's name/email directly.
  4. Resolve the amount:
     - If Amount > 0: use that amount.
     - If Amount = 0 and Recipient Type = Member: call getMemberDuesAmount_().
  5. Create and send the invoice via PayPal.
  6. Log to the Invoices sheet with Type = "Recurring".
  7. Update the "Last Sent" column.
```

The `Invoices.Type` column should expand from ["Dues", "Custom"] to ["Dues", "Custom", "Recurring"]. (Alternatively, just use "Recurring" for all scheduled sends and retire "Dues" — since member dues are now just one kind of recurring invoice. Either approach is valid; be consistent.)

Set up a time-based trigger that runs `processRecurringInvoices()` daily at a configured hour. The function itself determines which schedules are due today.

#### 4.9 Retire `sendMonthlyInvoices()` and `autoSendMonthlyInvoices()`

Once the Recurring Invoices engine is working, these functions become redundant. Keep `sendInvoiceToSelected()` as a convenience for one-off dues invoices, but update it to use `getMemberDuesAmount_()`.

**Test guidance:**

- **Schedule detection tests:** Create schedules with various frequencies and Day of Month values. Mock today's date (or use a helper that accepts a date parameter). Verify the processor correctly identifies which schedules should fire.
- **Double-send prevention:** Run `processRecurringInvoices()` twice on the same day. Verify only one invoice is created per schedule.
- **Member resolution:** Create a schedule for Member "M001", then change M001's email on the Members sheet. Verify the next invoice goes to the new email.
- **Amount resolution:** Create a member with a dues override of $40. Create their recurring schedule with Amount = 0. Verify the invoice is for $40. Remove the override; verify it falls back to the tier default.
- **Paused/Left members:** Pause a member. Verify their recurring schedule does not fire. Reactivate them; verify it resumes.
- **External recipients:** Create a recurring schedule for a non-member (Recipient Type = External). Verify invoices are created with the row's name/email.
- **PayPal sandbox:** All of the above should work end-to-end in sandbox mode before going live.

---

### Phase 3: Overdue Notices

**Goal:** Automatically send overdue reminder emails via Gmail when invoices pass their due date.

#### 4.10 Add Due Date to Invoices Sheet

Add a new column to the Invoices sheet: **"Due Date"** (insert after "Date Sent", before "Status"). This shifts Status to column K, Date Paid to column L, PayPal Invoice ID to column M, PayPal Invoice URL to column N. **Write a migration function** for this column shift, following the same pattern as `migrateInvoicesSheet()`.

The due date is:
- For recurring invoices: derived from the schedule's "Day of Month (Due)".
- For custom invoices: a new optional column on the Custom Invoices staging sheet. Defaults to "Due on receipt" (same day as sent) if blank.

Also pass the `due_date` field to the PayPal invoice payload:
```javascript
detail: {
  payment_term: {
    term_type: "DUE_ON_OTHER",
    due_date: "2026-03-15",  // YYYY-MM-DD format
  }
}
```

#### 4.11 Overdue Detection and Notification

Write `checkOverdueInvoices()`:

```
For each invoice where Status = "Sent" and Due Date is in the past:
  1. Calculate days overdue = today - Due Date.
  2. Look up the overdue notice threshold:
     a. If the invoice came from a Recurring schedule, check that schedule's "Overdue Notice (days)" column.
     b. Otherwise, use the Config default.
  3. If days overdue >= threshold AND no overdue notice has been sent yet:
     a. Send an email via GmailApp to the recipient.
     b. Update the invoice Status from "Sent" to "Overdue".
     c. Log the overdue notice (see §4.12).
```

The overdue email should be sent from the organization's Gmail account (the one running the script) using `GmailApp.sendEmail()` with `name` set to the org name.

Add a column to the Invoices sheet: **"Overdue Notice Sent"** (date, blank until sent). This prevents sending multiple overdue notices for the same invoice. (If you want to support multiple reminders, e.g., 14 days and 30 days, use a count or comma-separated date list instead.)

#### 4.12 Overdue Notices Log

Add rows to the Audit Log (or create a dedicated "Notifications Log" sheet — either approach works):

```
Timestamp | Invoice # | Recipient Email | Notice Type | Details
2026-03-16 09:00 | MEM-2026-03-001 | jane@example.com | Overdue | 14 days past due ($50.00)
```

Attach `checkOverdueInvoices()` to the same hourly trigger as `checkPaymentStatus()`, or create a separate daily trigger.

**Test guidance:**

- Create an invoice with a due date in the past (e.g., 15 days ago). Run `checkOverdueInvoices()`. Verify: (a) email sent, (b) status updated to "Overdue", (c) overdue notice date recorded, (d) log entry created.
- Run it again. Verify no second email is sent.
- Create an invoice 10 days overdue with a 14-day threshold. Verify no notice is sent yet. Advance the mock date to day 14; verify it fires.
- Verify that if a payment comes in (status changes to "Paid" via the payment check), no overdue notice is sent even if the invoice was overdue.

---

### Phase 4: Manual Payment Recording with PayPal Sync

**Goal:** When an invoice is paid by check, cash, or other off-PayPal method, mark it paid in the Sheet and push that status to PayPal so PayPal doesn't send its own overdue notices.

#### 4.13 Enhance `markSelectedPaid()`

Currently this function only updates the Sheet. Extend it to:

1. Prompt the user for payment method: "PayPal" (already paid via PayPal — just recording), "Check", "Cash", "Other".
2. Update the Sheet: set Status = "Paid", Date Paid = today, and add a new **"Payment Method"** column value.
3. If the invoice has a PayPal Invoice ID, call PayPal's Record Payment API:

```
POST /v2/invoicing/invoices/{invoice_id}/payments
{
  "method": "OTHER",
  "payment_date": "2026-02-23",
  "amount": { "currency_code": "USD", "value": "50.00" },
  "note": "Paid by check"
}
```

This marks the invoice as paid in PayPal, preventing PayPal from sending its own reminders.

#### 4.14 New Invoices Sheet Column: Payment Method

Add after "Date Paid": **"Payment Method"** — values: "PayPal", "Check", "Cash", "Other", or blank. Auto-set to "PayPal" when payment is detected by `checkPaymentStatus()`.

**Test guidance:**

- In sandbox mode, create and send an invoice. Before paying it via PayPal, use `markSelectedPaid()` to record a check payment. Verify: (a) Sheet updated, (b) PayPal API called with `method: "OTHER"`, (c) PayPal shows the invoice as paid when you query its status.
- Test the case where the PayPal API call fails (e.g., wrong invoice ID). Verify the Sheet is still updated with a warning note.

---

### Phase 5: Automated Backup System

**Goal:** Periodically copy all sheets to a separate, read-only Google Spreadsheet as a plain-text backup.

#### 4.15 Backup Function

Write `backupAllSheets()`:

1. Read the Backup Spreadsheet ID from the Config sheet.
2. Open the backup spreadsheet using `SpreadsheetApp.openById()`.
3. For each sheet in the source spreadsheet (Config, Members, Invoices, Recurring Invoices, Audit Log, Custom Invoices, Dashboard):
   a. If a sheet with that name exists in the backup, clear it.
   b. If not, create it.
   c. Copy all values (not formulas — use `getValues()` / `setValues()` to flatten to plain text).
   d. Also copy number formats so dates and currency display correctly.
4. Add a "Backup Metadata" sheet in the backup with: backup timestamp, source spreadsheet URL, and row counts per sheet.
5. Protect all sheets in the backup spreadsheet (set to "Warning" protection so the admin can still access in emergencies, but accidental edits are discouraged).

#### 4.16 Backup Trigger

Add a menu item: **"🗄️ Run Backup Now"** and a trigger option **"⏰ Enable Weekly Backup"** that runs `backupAllSheets()` every Sunday at 2 AM.

#### 4.17 Setup

The admin creates a blank Google Spreadsheet, copies its ID (from the URL), and pastes it into the Config sheet's "Backup Spreadsheet ID" row.

**Test guidance:**

- Run backup with 3 sheets containing sample data. Open the backup spreadsheet. Verify all data matches, dates are formatted correctly, and the metadata sheet shows correct row counts.
- Modify the source data. Run backup again. Verify the backup reflects the changes (it's a full overwrite, not incremental).
- Test with an invalid Backup Spreadsheet ID. Verify a clear error message is shown.

---

### Phase 6: Dashboard and Reporting Enhancements

**Goal:** The dashboard reflects all new data sources and provides useful financial summaries.

#### 4.18 Updated Dashboard Sections

1. **Membership Overview:** Active (Full/Hardship breakdown with actual revenue contribution using per-member rates, not just tier defaults × count), Paused, Left.
2. **Current Month:** Invoices sent (Recurring/Custom breakdown), paid, outstanding, overdue.
3. **Accounts Receivable Aging:** Invoices 0–30 days outstanding, 31–60, 61–90, 90+ days.
4. **All-Time Totals:** With collection rate, total revenue by type (Dues/Custom/Recurring), and revenue by quarter.
5. **Upcoming:** Next recurring invoices due to send (from Recurring Invoices sheet).
6. **Last Backup:** Timestamp of most recent backup.

**Test guidance:** Populate test data covering various statuses, dates, and amounts. Refresh the dashboard. Verify every number matches a manual count of the underlying data.

---

## 5. Implementation Order & Dependencies

```
Phase 1 (Member Data)
  ├── 4.1 Expand Members Sheet
  ├── 4.2 Audit Log Sheet
  ├── 4.3 Per-member dues logic
  ├── 4.4 Config updates
  └── 4.5 Migration function
        │
Phase 2 (Recurring Invoices) — depends on Phase 1
  ├── 4.6 Recurring Invoices Sheet
  ├── 4.7 Auto-populate schedules
  ├── 4.8 Recurring invoice processor
  └── 4.9 Retire old monthly functions
        │
Phase 3 (Overdue Notices) — depends on Phase 2
  ├── 4.10 Due Date column + migration
  ├── 4.11 Overdue detection
  └── 4.12 Notifications log
        │
Phase 4 (Manual Payment Sync) — can run in parallel with Phase 3
  ├── 4.13 Enhanced markSelectedPaid()
  └── 4.14 Payment Method column
        │
Phase 5 (Backup) — independent, can run anytime
  ├── 4.15 Backup function
  ├── 4.16 Backup trigger
  └── 4.17 Setup
        │
Phase 6 (Dashboard) — depends on everything above
  └── 4.18 Updated dashboard
```

**Recommended implementation order:** Phase 5 first (it's independent and protects existing data), then Phase 1 → 2 → 3 & 4 (parallel) → 6.

---

## 6. Testing Strategy

Google Apps Script does not have a built-in test framework, but effective testing is still possible. Here is the recommended approach.

### 6.1 Test Harness Pattern

Create a separate file in the Apps Script project called `Tests.gs`. Use this pattern:

```javascript
function runAllTests() {
  const results = [];
  results.push(test_getMemberDuesAmount());
  results.push(test_generateInvoiceNumber());
  results.push(test_scheduleDetection());
  // ... add more

  const passed = results.filter(r => r.passed).length;
  const failed = results.filter(r => !r.passed).length;
  Logger.log("Tests: " + passed + " passed, " + failed + " failed.");
  results.filter(r => !r.passed).forEach(r => Logger.log("FAIL: " + r.name + " — " + r.reason));

  SpreadsheetApp.getUi().alert(
    "Test Results",
    passed + " passed, " + failed + " failed.\n\nSee Apps Script logs for details.",
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

function test_getMemberDuesAmount() {
  const name = "getMemberDuesAmount: override takes precedence";
  try {
    const config = { FULL_RATE: 50, HALF_RATE: 25 };
    const member = { tier: "Full", duesOverride: 40 };
    const result = getMemberDuesAmount_(member, config);
    if (result !== 40) return { name, passed: false, reason: "Expected 40, got " + result };
    return { name, passed: true };
  } catch (e) {
    return { name, passed: false, reason: e.message };
  }
}
```

Add a menu item: **"🧪 Run Tests"** (only visible in sandbox mode, gated by `if (getConfig().PAYPAL_MODE === "sandbox")`).

### 6.2 What to Test — Checklist

**Pure logic (no API calls, no Sheet reads — fast, reliable):**
- `getMemberDuesAmount_()` — override vs. tier default vs. fallback.
- `generateInvoiceNumber()` — sequential numbering, month rollover.
- `formatMonthYear()` — various dates.
- Schedule detection logic — should this schedule fire today? Test monthly, quarterly, annually; test "already sent today" prevention; test start/end date boundaries.
- Overdue detection — days calculation, threshold comparison.

**Sheet integration (reads/writes sheets — use a test sheet):**
- `getActiveMembers()` — filters Active, skips Paused/Left, reads new columns.
- `logInvoice_()` — verify row written with correct column alignment (this is where field-mismatch bugs like the one we hit in development occur).
- `logAuditEntry_()` — verify row appended to Audit Log.
- `backupAllSheets()` — verify backup spreadsheet content matches source.
- Column alignment: for each sheet, verify that reading row N and mapping to an object produces the correct field values. This catches the class of bug where code expects column F to be "Amount" but it's actually "Description" due to a column insertion.

**PayPal integration (requires sandbox — slower, may have latency):**
- `testPayPalConnection()` — already exists.
- Create a draft invoice, verify it appears in PayPal.
- Send an invoice, verify PayPal status is SENT.
- Record a payment via the API, then run `checkPaymentStatus()`, verify Sheet updates.
- Cancel an invoice, verify PayPal status is CANCELLED.

### 6.3 Test Data Setup

Write a `setupTestData()` function that:
1. Clears all sheets.
2. Re-initializes with `initializeSheets()`.
3. Inserts 5 test members with varied tiers, statuses, and dues overrides.
4. Inserts 3 recurring schedules (monthly member dues, quarterly external, one inactive).
5. Inserts 5 invoices with varied statuses and dates.

This function should be idempotent — safe to run repeatedly.

### 6.4 Column Alignment Safety Net

The single most common bug in this codebase has been column index mismatches after adding or inserting columns. Establish this defensive pattern:

```javascript
// Define column indices as named constants, one place
const INV_COLS = {
  INVOICE_NUM: 0, TYPE: 1, MEMBER_ID: 2, NAME: 3, EMAIL: 4,
  DESCRIPTION: 5, AMOUNT: 6, MONTH_YEAR: 7, DATE_SENT: 8,
  STATUS: 9, DATE_PAID: 10, PAYPAL_ID: 11, PAYPAL_URL: 12,
};
```

Use these everywhere instead of magic numbers. When a column is added, update the constants in one place.

Write a test that reads the header row and verifies each constant maps to the expected header string. If this test fails, you know the constants are out of sync before any data gets corrupted.

---

## 7. Architectural Advice for the Next Developer

### 7.1 Keep Functions Small and Pure Where Possible

Separate "decide what to do" from "interact with Sheet" from "interact with PayPal". The current code mixes these concerns in some places (e.g., `sendMonthlyInvoices` reads sheets, calls PayPal, writes sheets, and shows UI in one function). Where practical, extract the logic into testable helpers.

### 7.2 The Column Index Problem

As noted, the most frequent source of bugs has been column indices getting out of sync after inserting columns. The named constants approach (§6.4) is essential. Additionally, every migration function should include a header-detection step at the top that verifies the current layout before acting.

### 7.3 Google Apps Script Execution Limits

- **6-minute execution limit** for user-triggered functions (30 minutes for time-based triggers on Workspace accounts, 6 minutes on free accounts).
- If the organization grows beyond ~100 members, `processRecurringInvoices()` may approach the limit due to sequential PayPal API calls. Consider batching or chunking if this becomes an issue.
- `UrlFetchApp` has a daily quota of ~20,000 calls for free accounts, ~100,000 for Workspace.

### 7.4 Error Handling Philosophy

PayPal API calls can fail for transient reasons. The current code logs errors and continues to the next member. This is correct — one failed invoice should not block the rest. Always wrap PayPal calls in try/catch at the per-item level.

### 7.5 The "Hardship" Rename

The v1/v2 code uses "Half" as the tier name. The organization's actual term is "Hardship". Phase 1 renames this. All code references to "Half" must be updated. Search the codebase for "Half" (case-sensitive) to find every reference. The Config sheet label "Half Rate ($)" becomes "Hardship Rate ($)".

### 7.6 Avoid Scope Creep on the Recurring Engine

The recurring invoices engine (Phase 2) is the most complex new subsystem. Implement it for Monthly, Quarterly, and Annually first. Do not attempt to support "every N days" or "biweekly" — these are unlikely to be needed and significantly complicate the scheduling logic.

### 7.7 PayPal Invoicing API Reference

- **Create draft:** `POST /v2/invoicing/invoices`
- **Send invoice:** `POST /v2/invoicing/invoices/{id}/send`
- **Get invoice:** `GET /v2/invoicing/invoices/{id}`
- **Cancel invoice:** `POST /v2/invoicing/invoices/{id}/cancel`
- **Record payment:** `POST /v2/invoicing/invoices/{id}/payments`
- **Generate next number:** `POST /v2/invoicing/generate-next-invoice-number`
- **Full docs:** https://developer.paypal.com/docs/api/invoicing/v2/

### 7.8 User Preferences Note

The commissioning user has expressed a preference for Scheme and miniKanren where possible. While Google Apps Script is JavaScript-only (so the production code must be JS), any auxiliary tooling, data validation logic, or offline analysis scripts written outside the GAS environment could use Scheme if the developer is comfortable with it. This is not a requirement for the GAS code itself.
