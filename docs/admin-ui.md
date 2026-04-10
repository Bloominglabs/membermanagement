# Staff Admin UI Plan

## Goal

Provide a staff-only administrative UI that is:

- thin
- obvious
- fast to maintain
- complete enough that no important operation is hidden behind indirect navigation

The UI must not become a second application with duplicated business logic. The backend remains authoritative.

## Constraints

- No SPA is required.
- No workflow may exist only in the frontend.
- Every write operation must terminate in an existing Django service, model admin action, API endpoint, or management command.
- Staff must always have a direct route to the raw record, audit trail, and related objects.
- The UI is for staff only, not members or the public.

## Recommended Technical Shape

Build a small Django app for staff operations, for example `apps.staffops`, using:

- Django templates
- server-rendered views
- standard POST forms
- very small amounts of vanilla JavaScript only where it improves usability

Avoid introducing a frontend framework unless there is a concrete need that the server-rendered approach cannot meet.

## Design Rules

### 1. Backend-authoritative

- All business rules stay in service functions and backend views.
- The staff UI may collect parameters and display results, but it should not calculate balances, determine status changes, or perform allocation logic client-side.

### 2. No hidden paths

- Every operational action gets a stable URL.
- Every major screen includes direct links to:
  - raw Django admin object
  - related records
  - API endpoint or export when useful
  - audit/history view

### 3. Support power use

- Search must be global across members, clients, invoices, payments, and RFID credentials.
- Lists must support filters, sort order, and CSV export where the underlying API already supports it.
- Bulk actions are preferred over repetitive click-through flows for common operations.

### 4. Preserve escape hatches

- Django admin remains available for raw CRUD, support, and inspection.
- The custom staff UI is a workflow layer, not a replacement for admin.

### 5. Readability over polish

- Use plain layouts, dense tables, direct labels, and explicit action buttons.
- Do not hide important data in accordions or modal-only flows.

## Recommended Information Architecture

Top-level staff navigation:

- Home
- Members
- Billing
- Donations
- Expenses
- Access
- Reports
- Audit
- Admin

The `Admin` entry should link directly to Django admin as the raw-system fallback.

## Workflow Split

### Keep in Django Admin

These are low-frequency or raw-record tasks where standard model admin is acceptable:

| Area | Task | Why admin is enough |
|---|---|---|
| Members | Direct CRUD on `Client`, `Member`, `MembershipTerm`, `ClientAlias` | Mostly record-oriented; useful as raw fallback |
| Billing | Inspect `WebhookEvent`, `ProcessorCustomer`, `ProcessorPaymentMethod`, `Allocation`, `MemberBalanceSnapshot` | Operational inspection rather than guided workflow |
| Donations | Inspect raw donation records | Read-mostly, low-complexity |
| Ledger | Inspect `Account`, `JournalEntry`, `JournalLine` | Accounting support and diagnostics |
| Access | Inspect `AccessAllowlistSnapshot`, `AccessEvent` raw rows | Useful for debugging |
| Audit | Inspect append-only `AuditLog` | Read-only support/debug function |

### Build as Custom Thin Staff Pages

These are the places where plain admin becomes circuitous or hides the real workflow:

| Area | Workflow | Why it needs a custom page |
|---|---|---|
| Members | Unified member workspace | Staff need one screen showing identity, status, balance, invoices, payments, history, RFID, and actions |
| Members | Member search / queue views | Staff need direct lists like Active, Past Due, Suspended, Autopay Enabled |
| Billing | Billing operations console | Monthly close, autopay run, reconciliation checks, and invoice schedule runs are operational commands, not row edits |
| Billing | Invoice / payment review lists | Staff need filters and direct resolution actions without hopping across models |
| Expenses | CSV import and review | Import, dedupe, categorize, and reconcile is a workflow, not raw CRUD |
| Access | Credential and allowlist operations | Staff need member-centric access management and snapshot refresh/status views |
| Reports | Treasurer reporting | Staff need a stable, direct place for financial, balances, aging, and CSV exports |
| Audit | Cross-object timeline view | Admin raw tables are not enough for timeline-style investigation |

### Support in Both

| Area | Workflow | Use both |
|---|---|---|
| Members | Create/edit member | Custom page for common workflow, admin for raw access |
| Billing | Create/edit invoice schedules | Custom filtered list for normal use, admin for raw edits |
| Access | RFID credential CRUD | Custom member page for day-to-day, admin for direct inspection |
| Expenses | Rule/category maintenance | Admin is fine initially, custom page later if rule volume grows |

## Required Custom Screens

### 1. Staff Home

Purpose: one obvious landing page for all staff actions.

Show:

- counts for active, past-due, suspended members
- counts for overdue invoices and unreconciled expenses
- latest allowlist snapshot time
- latest webhook failures or invalid signatures
- direct action buttons

Primary actions:

- open member search
- run monthly dues close
- run autopay
- refresh allowlist
- import expense CSV
- open reports

### 2. Member Search

Purpose: replace indirect navigation through separate client, member, invoice, and payment pages.

Required filters:

- name/email/member number
- membership status
- membership class
- autopay enabled
- door access enabled

Columns:

- member number
- name
- status
- class
- receivable
- credit
- autopay
- door access
- last updated

Each row links to the member workspace.

### 3. Member Workspace

Purpose: the primary staff screen.

Sections on one page:

- identity and contact information
- current membership state
- current balance summary
- current RFID credentials
- latest membership term
- recent invoices
- recent payments
- audit/history summary
- direct links to raw admin objects

Primary actions:

- edit member
- record manual payment
- issue one-off invoice
- open invoice schedules
- change status only if policy allows manual override
- enable/disable door access
- add/deactivate RFID credential
- open raw admin records

This page should reduce the need to jump across multiple admin models.

### 4. Billing Operations Console

Purpose: direct access to system-level billing actions.

Show:

- latest run times
- current overdue invoice count
- count of Stripe payments pending reconciliation
- count of autopay-enabled members

Actions:

- run monthly dues close
- run scheduled invoice generation
- run autopay
- run member status enforcement
- run Stripe reconciliation check

For each action, show:

- parameters if any
- confirmation prompt
- result summary
- link to affected records

This page should call backend services or wrap existing management commands in staff-only views.

### 5. Invoice and Payment Review

Purpose: operational review without raw model hopping.

Invoice list filters:

- status
- type
- due date range
- member/client

Payment list filters:

- status
- source type
- processor
- received date range
- unreconciled Stripe only

Actions:

- view allocations
- manually allocate a payment
- issue/void invoice
- open member workspace
- open raw admin

### 6. Expense Import and Review

Purpose: make CSV import usable as an operational workflow.

Screens:

- import form
- import batch detail
- uncategorized transaction queue
- categorized-but-unreconciled queue

Actions:

- upload CSV
- review duplicate flags
- apply category
- mark reconciled
- jump to matching rules

### 7. Access Operations

Purpose: make door access management member-centric and explicit.

Show:

- credential roster
- allowlist snapshot age
- recent access events

Actions:

- add/deactivate RFID credential
- refresh allowlist snapshot
- inspect last exported payload
- open member entitlement view

If the on-prem agent matures later, this screen can also show its last poll/health state.

### 8. Reports

Purpose: a direct staff destination for Treasurer use.

Required reports:

- financial report
- member balances
- A/R aging

Each report page should offer:

- date inputs where applicable
- rendered summary
- CSV export links
- direct links to underlying invoice/payment/member lists

### 9. Audit Timeline

Purpose: investigation without raw database browsing.

Filters:

- entity type
- entity id
- action
- date range

Show:

- occurred time
- actor
- action
- before/after diff summary
- links to raw entity

## Implementation Guidance

### Use the existing backend first

Prefer to build the staff UI on current endpoints and services:

- member history and balance endpoints
- invoice and payment endpoints
- manual payment endpoint
- access allowlist and event endpoints
- report and export endpoints

If a staff workflow needs data composition not currently exposed cleanly, add a backend view for that composition. Do not push composition complexity into browser code.

### Add staff-only views, not public views

- Require authenticated staff access for all custom pages.
- Keep these pages under a clear namespace such as `/staff/`.

### Give every page raw links

Every custom page should include:

- `Open in admin`
- `Open related records`
- `Open audit history`

This directly addresses the FreshBooks-style failure mode where capabilities become hidden behind UI choices.

### Prefer explicit actions over smart automation

For staff tooling:

- label actions clearly
- show exactly what will happen
- return concrete counts and record links

Avoid opaque “fix everything” buttons.

## Suggested Delivery Order

Phase 1:

- staff home
- member search
- member workspace
- billing operations console

Phase 2:

- invoice/payment review
- reports screens
- expense import/review

Phase 3:

- access operations
- audit timeline
- optional admin polish for heavy-use models

## Minimum Definition of Done

The thin staff UI is successful when:

- a staff user can perform common member-management tasks from direct URLs without model-hopping
- no critical action is hidden behind Django admin knowledge alone
- all important screens expose raw-record escape hatches
- business logic still lives in backend services
- the UI remains small enough that a Django developer can maintain it without a dedicated frontend stack
