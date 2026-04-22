# Bloominglabs Membership, Clients, Billing, and Finance System

Reference implementation seed. This document remains useful background, but [`spec.md`](./spec.md), [`architecture.md`](./architecture.md), and the ADRs are the current source of truth.

## Codex Implementation Specification v1

### 1. Product goal

Build a self-hosted, host-portable system for Bloominglabs that replaces FreshBooks for membership billing, credit/debt tracking, client history, donation intake recording, expense tracking, and financial reporting, while exposing modular interfaces for future RFID and bank-import components.

This system must become the authoritative system for:

- clients and client history
- members and membership history
- dues charging and payment application
- prepayments and arrears
- donations and designations
- other income and categorized expenses
- continuously generated financial reports over arbitrary time ranges

### 2. Architecture decision

Use a modular monolith:

- Backend: Django + Django REST Framework
- Database: Postgres
- Async jobs: Celery + Redis
- Packaging: Docker Compose
- Optional on-prem component later: access-agent for RFID/door sync

Deployment units:

- `app` — Django API + staff UI
- `db` — Postgres
- `redis` — job broker/cache
- `worker` — Celery worker
- `scheduler` — Celery beat
- `reverse_proxy` — optional
- `access_agent` — separate future/on-prem package, not required for v1

### 3. Domain model

#### 3.1 Core principle: Client is the superset

A Client is any entity that financially interacts with Bloominglabs. A Member is a subtype extension of Client.

#### 3.2 Entity overview

##### Client

Fields:

- `id`
- `client_type`: `PERSON` | `ORGANIZATION`
- `display_name`
- `legal_name`
- `primary_email`
- `primary_phone`
- `address_line1`
- `address_line2`
- `city`
- `state`
- `postal_code`
- `country`
- `notes`
- `is_active`
- `created_at`
- `updated_at`

##### ClientAlias

Fields:

- `id`
- `client_id`
- `alias_type`: `NAME` | `EMAIL` | `PHONE` | `ADDRESS`
- `value`
- `valid_from`
- `valid_to`

##### Member

Fields:

- `id`
- `client_id` unique FK
- `member_number`
- `membership_status`: `APPLICANT` | `ACTIVE` | `PAST_DUE` | `SUSPENDED` | `LEFT`
- `membership_class`: `FULL` | `HARDSHIP`
- `voting_eligible`
- `door_access_enabled`
- `joined_on`
- `left_on`
- `autopay_enabled`
- `stripe_customer_id`
- `default_payment_method_id`
- `notes`

##### MembershipTerm

Fields:

- `id`
- `member_id`
- `effective_from`
- `effective_to`
- `membership_class`
- `monthly_dues_cents`
- `voting_eligible`
- `door_access_enabled`
- `reason`

### 4. Dues policy model

Configurable values:

- `full_dues_cents` default `5000`
- `hardship_dues_cents` default `2500`
- `default_hardship_ratio` default `0.5` for UI suggestion only
- `default_member_invoice_day` default `1`
- `default_member_due_day` default `15`
- `default_member_due_offset_days` default `14`
- `suspension_threshold_months` default `3`

Important rule:

Hardship is not computed live as half of full. It is separately stored and configurable. The 2:1 ratio is only the default initial setting.

Support two schedule styles:

- Member dues schedule
- Generic invoice schedule with specific generation day, specific due day, or due offset in days, monthly/quarterly/annual recurring ad-hoc invoices, and one-off invoices

### 5. Financial data model

Separate:

- charges
- cash receipts
- allocations
- journal entries

#### Operational subledger tables

##### Invoice

Fields:

- `id`
- `client_id`
- `member_id` nullable
- `invoice_type`: `MEMBER_DUES` | `RECURRING_AD_HOC` | `ONE_OFF`
- `invoice_number`
- `issue_date`
- `due_date`
- `service_period_start`
- `service_period_end`
- `status`: `DRAFT` | `ISSUED` | `PARTIALLY_PAID` | `PAID` | `VOID` | `OVERDUE`
- `currency`
- `total_cents`
- `external_processor`: `STRIPE` | `EVERYORG` | `NONE`
- `external_reference`
- `notes`

##### InvoiceLine

Fields:

- `id`
- `invoice_id`
- `line_type`: `DUES` | `TOOL_FEE` | `ROOM_FEE` | `SUPPLY` | `OTHER`
- `description`
- `quantity`
- `unit_price_cents`
- `line_total_cents`
- `income_category_id` nullable
- `service_period_start`
- `service_period_end`

##### Payment

Fields:

- `id`
- `client_id`
- `member_id` nullable
- `received_at`
- `amount_cents`
- `currency`
- `payment_method`: `STRIPE_CARD` | `STRIPE_ACH` | `CASH` | `CHECK` | `BANK_TRANSFER` | `EVERYORG` | `OTHER`
- `processor_event_id`
- `processor_charge_id`
- `status`
- `notes`

##### Allocation

Fields:

- `id`
- `payment_id`
- `invoice_id`
- `invoice_line_id` nullable
- `allocated_cents`
- `allocated_at`

##### MemberCreditLedger

Fields:

- `id`
- `member_id`
- `entry_type`: `PAYMENT_IN` | `CHARGE_OUT` | `MANUAL_ADJUSTMENT` | `REVERSAL`
- `delta_cents`
- `effective_at`
- `reference_type`
- `reference_id`
- `memo`

### 6. General ledger model

#### Account

Fields:

- `id`
- `code`
- `name`
- `account_type`: `ASSET` | `LIABILITY` | `INCOME` | `EXPENSE` | `EQUITY`
- `is_active`

Starter accounts:

- `ASSET:BANK:CHECKING`
- `ASSET:STRIPE_CLEARING`
- `ASSET:ACCOUNTS_RECEIVABLE`
- `LIABILITY:MEMBER_PREPAYMENTS`
- `INCOME:DUES`
- `INCOME:DONATIONS`
- `INCOME:OTHER`
- `EXPENSE:RENT`
- `EXPENSE:ELECTRICITY`
- `EXPENSE:GAS`
- `EXPENSE:TRASH`
- `EXPENSE:INTERNET`
- `EXPENSE:TOOLS`
- `EXPENSE:SUPPLIES`

#### JournalEntry

Fields:

- `id`
- `entry_date`
- `description`
- `source_type`
- `source_id`
- `external_reference`
- `created_at`

#### JournalLine

Fields:

- `id`
- `journal_entry_id`
- `account_id`
- `amount_cents` signed
- `client_id` nullable
- `member_id` nullable
- `designation_id` nullable
- `expense_category_id` nullable
- `memo`

Constraint:

- every journal entry must sum to zero

### 7. Reporting model

Two accounting views are required:

- Earned dues view
- Cash basis view

Each payment must preserve source semantics:

- payment toward current invoice
- prepayment credit
- debt catch-up
- donation
- other income

`GET /api/reports/financial?from=YYYY-MM-DD&to=YYYY-MM-DD`

Response sections:

- Summary
- Dues section
- Donations section
- Expenses section
- Balance snapshot

### 8. Stripe integration spec

Use Stripe for:

- one-time dues payment
- autopay enrollment
- off-session recurring dues charging
- prepayment/top-up credit
- pay-balance flows

Objects:

- `Customer`
- `Checkout Session`
- `SetupIntent`
- `PaymentIntent`
- webhooks

Webhook rules:

- verify `Stripe-Signature` using raw request body
- store processed event ids with unique constraint
- accept duplicate deliveries safely
- never assume event ordering
- use idempotency keys on outbound POSTs to Stripe

### 9. Every.org integration spec

Use Every.org only for donations.

Endpoint:

- `POST /webhooks/everyorg/nonprofit-donation/`

Persist:

- amount
- netAmount
- donationDate
- frequency
- designation
- donor info if shared
- `chargeId` as idempotency key

### 10. Expense import spec

Build a pluggable import interface.

#### BankImportSource

Fields:

- `id`
- `name`
- `parser_key`
- `is_active`

#### ImportedBankTransaction

Fields:

- `id`
- `source_id`
- `import_batch_id`
- `posted_on`
- `description_raw`
- `amount_cents`
- `direction`
- `currency`
- `external_hash`
- `is_duplicate`
- `is_reconciled`

#### ExpenseCategorizationRule

Fields:

- `id`
- `priority`
- `match_type`: `REGEX` | `CONTAINS` | `AMOUNT_RANGE`
- `pattern`
- `expense_category_id`
- `vendor_name`
- `active`

Initial formats:

- CSV required
- OFX/QFX optional next
- QIF optional later

### 11. RFID / access interface spec

Keep this as an interface only in v1.

Member-facing data:

- `door_access_enabled` boolean

Expose:

- `GET /api/access/allowlist`
- `GET /api/access/members/{member_id}/entitlement`
- signed snapshot/version metadata

### 12. History and audit requirements

Everything important must be historically reconstructable.

#### AuditLog

Fields:

- `id`
- `occurred_at`
- `actor_type`
- `actor_id`
- `entity_type`
- `entity_id`
- `action`
- `before_json`
- `after_json`
- `reason`

Track at minimum:

- client created/updated
- member joined
- member left
- member rejoined
- membership class changed
- dues amount changed
- autopay enabled/disabled
- door access enabled/disabled
- invoice issued/voided
- payment received/reversed
- allocation created/adjusted
- expense categorized/recategorized
- donation designation recorded/changed

### 13. TDD delivery contract

For each logical unit:

1. identify the behavior
2. write the failing test first
3. confirm failure
4. implement the minimum code
5. confirm pass
6. run full suite
7. refactor only with tests green

Required test layers:

- Unit tests
- Integration tests
- Property tests
- Migration tests
- Contract tests

### 14. Codex implementation phases

1. Foundation
2. Clients and members
3. Dues and invoicing
4. Payments and credit/debt
5. Stripe
6. Donations
7. Expenses
8. Ledger and reporting
9. Access interface

### 15. Key APIs

Clients:

- `GET /api/clients`
- `POST /api/clients`
- `GET /api/clients/{id}`
- `PATCH /api/clients/{id}`

Members:

- `GET /api/members`
- `POST /api/members`
- `GET /api/members/{id}`
- `PATCH /api/members/{id}`
- `GET /api/members/{id}/history`
- `GET /api/members/{id}/balance`

Invoices:

- `GET /api/invoices`
- `POST /api/invoices`
- `POST /api/invoices/{id}/issue`
- `POST /api/invoices/{id}/void`

Payments:

- `POST /api/payments/manual`
- `GET /api/payments`
- `POST /api/payments/{id}/allocate`

Stripe:

- `POST /api/stripe/create-checkout-session`
- `POST /api/stripe/create-setup-intent`
- `POST /webhooks/stripe`

Donations:

- `POST /webhooks/everyorg/nonprofit-donation`
- `POST /api/donations/manual`
- `GET /api/donations`

Expenses:

- `POST /api/expenses/import/csv`
- `GET /api/expenses/import-batches`
- `POST /api/expenses/{id}/categorize`

Reports:

- `GET /api/reports/financial`
- `GET /api/reports/member-balances`
- `GET /api/reports/ar-aging`

Access:

- `GET /api/access/allowlist`

### 16. Default business rules

- Full dues: `$50.00`
- Hardship dues: `$25.00`
- Full and Hardship independently configurable
- Dues monthly
- Default dues invoice issue date: 1st of month
- Default dues due date: 15th of month
- Members can prepay arbitrary amounts
- Prepayments apply FIFO to oldest unpaid dues
- Debt is unpaid allocated dues
- Door access is represented only as a flag in v1
- Slack has no entitlement automation in v1
- Donations are never mixed with dues logic
- All money is integer cents
- All financial mutations happen in DB transactions

### 17. Remaining unknowns to leave abstract

- exact IUCU CSV schema
- future on-prem RFID wire protocol
- whether later you want multiple door zones/controllers
- whether later you want OFX/QFX before or after CSV stabilization

### 18. Final recommendation

Implement a Dockerized Django/Postgres modular monolith with strict TDD, where Client is the financial superset and Member is a subtype; dues, payments, prepayments, debts, donations, other income, expenses, and reports are first-class; Stripe handles dues payments, Every.org handles donations, and door access plus bank import remain modular interfaces.

Do not model member balance as a mutable magic number. Model it from charges, payments, allocations, and journal postings.
