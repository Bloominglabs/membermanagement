# Payment Processors for Bloominglabs Membership Dues and Codex-Ready Integration Spec

## Executive summary

Bloominglabs’ dues system has unusually strict requirements for **auditability and modularity**: monthly dues (Full **$50/mo**, Hardship **$25/mo**, both configurable), **prepayments/credits** tracked over time, “client” as a superset of “member,” and a self-hosted **Django/Postgres modular monolith** that can outlive any SaaS vendor. The dues processor therefore must not become the ledger; it must be a **reliable payment rail with strong APIs and webhooks**, while Bloominglabs’ core system owns invoices, credit/debt, and reports.

**Single best-choice recommendation: Stripe (Payments + ACH Direct Debit), using Stripe webhooks + PaymentIntents/SetupIntents, while keeping Bloominglabs’ ledger authoritative.** Stripe’s US pricing is transparent (no setup/monthly fees; **2.9% + $0.30** for domestic cards), and ACH Direct Debit is **0.8% with a $5 cap**, materially reducing fees for dues if members use bank дебits. citeturn16search0turn16search2turn16search3 Stripe’s webhook tooling is unusually mature: it documents retries (up to **3 days**), explicit guidance on **duplicate events**, and explicitly states Stripe **doesn’t guarantee event delivery order**, which is exactly what you want for correctness-focused financial ingestion. citeturn23search0 Stripe is also independently certified as a **PCI Service Provider Level 1**, and provides guidance that maps integration approaches to PCI validation forms—critical for a small nonprofit that wants to minimize compliance burden. citeturn11search0turn11search3

A key cost-control detail: **avoid Stripe Billing unless you truly need its subscription/billing product features**, because Stripe Billing adds a **0.7% fee on Billing volume** (pay-as-you-go plan). For Bloominglabs, you can implement monthly dues charges yourself (in Django) and use Stripe purely for payment collection (Checkout/Payment Element + SetupIntent + off-session PaymentIntent), which avoids that extra margin while preserving flexibility for prepayments and ad-hoc invoicing. citeturn17view0turn29search1

### Fee math examples using Stripe standard rates

Stripe card pricing and ACH pricing are taken from Stripe’s official pricing pages. citeturn16search0turn16search2turn16search3

| Example charge | Stripe card fee (2.9% + $0.30) | Net after card fees | Stripe ACH fee (0.8%, cap $5) | Net after ACH fees |
|---:|---:|---:|---:|---:|
| $10.00 | $0.59 | $9.41 | $0.08 | $9.92 |
| $25.00 | $1.03 (2.9% = $0.725 + $0.30) | $23.97 | $0.20 | $24.80 |
| $100.00 (one‑time) | $3.20 | $96.80 | $0.80 | $99.20 |

Interpretation for Bloominglabs: on small transactions, **ACH is dramatically cheaper than cards**, so the membership portal should nudge members toward ACH autopay (while keeping cards available). Stripe’s ACH Direct Debit settlement has delays (standard “T+4” availability; “T+2” for eligible accounts), and is not a guaranteed instrument, so your ledger and access logic must treat “initiated” vs “settled/failed” explicitly. citeturn0search0turn0search1turn0search6

## Ranked shortlist of acceptable dues processors

### Stripe

Stripe is the strongest fit for Bloominglabs’ “payment rail, not ledger” goal because its API primitives map cleanly to your own invoice + credit/debt model: **PaymentIntents** for payments, **SetupIntents** for saving payment methods for autopay, and webhooks for asynchronous truth. citeturn29search1turn23search0 Stripe’s US pricing is pay-as-you-go with **no monthly fees** and **2.9% + $0.30** for domestic cards. citeturn16search0 For low-fee bank debits, Stripe offers **ACH Direct Debit at 0.8% capped at $5**, and documents settlement timing and risk properties (delayed confirmation, possible post-success failures, disputes/returns behavior). citeturn16search2turn0search0turn0search1 Its webhook model is robust: Stripe retries deliveries for up to **three days**, recommends deduplicating by event IDs, and explicitly warns that event order is **not guaranteed**, which pushes you toward correct idempotent ingestion. citeturn23search0turn16search4 Settlement/payout behavior is well-documented (initial payout typically **7–14 days** after first payment; thereafter per payout schedule). citeturn16search1turn16search6 Notable limitation: Stripe Billing adds **0.7% of Billing volume**, so for dues you should either (a) implement recurring charges yourself with off-session PaymentIntents or (b) consciously accept the extra cost if Stripe Billing features are worth it. citeturn17view0turn29search1

### PayPal Braintree

PayPal Braintree is a compelling alternative if you want strong coverage of wallets and PayPal ecosystem features with a developer-friendly gateway. Official US fee tables publish **2.89% + $0.29** for card and third‑party digital wallet transactions (standard), plus a discounted **charity rate of 2.19% + $0.29** for verified 501(c)(3) organizations, and **ACH Direct Debit at 0.75% (cap $5)**. citeturn8search0 It supports multiple payment method types (cards, Apple Pay, Google Pay, PayPal, Venmo; and US bank accounts via ACH Direct Debit, subject to eligibility and integration method). citeturn15search1turn7search3turn7search5 Funding guidance is documented: “typically… within **2–5 business days after the transaction has settled**” for credit cards (timelines vary by setup), and ACH has its own timeline (Braintree describes a 3‑day return waiting period plus disbursement, totaling about **5 business days**). citeturn9search3turn9search5 Webhooks are signed and parsed via `bt_signature`/`bt_payload`, are not guaranteed sequential, and are retried up to **24 hours** in production. citeturn2search5turn2search4 Limitations: PayPal transactions are “subject to PayPal Merchant Fees” (PayPal-controlled), and merchant availability is limited to specific domiciles/countries (Braintree Direct availability list includes US, Canada, Australia, Europe, Singapore, Hong Kong, Malaysia, New Zealand). citeturn8search0turn15search3

### Square

Square is a strong “all-in-one” alternative, especially if Bloominglabs wants in-person point-of-sale alongside online dues, and it offers good APIs and webhooks. Square’s pricing for **Online API** payments is published at **2.9% + $0.30**, and Square supports **ACH via API** (Web Payments SDK + Payments API) at **1% with $1 minimum and $5 cap**. citeturn1search1turn1search0 Square’s standard deposit schedule is next-business-day under typical conditions, with optional instant/same-day transfers for a fee (e.g., instant transfers described at **1.75%** in US support docs). citeturn6search0 Square webhooks include an `event_id` for idempotency/deduplication, and Square documents that webhook notifications can be sent more than once; it also provides explicit signature verification using `x-square-hmacsha256-signature` derived from signature key + notification URL + raw body. citeturn2search1turn2search0 Square provides a Subscriptions API, but critically **ACH is not available through the Subscriptions API** because bank account sources can’t be stored on file and charged later—this is a real limitation for “ACH autopay monthly dues,” pushing you toward card-on-file or invoice-based ACH rather than true ACH autopay. citeturn25search0turn25search7 Square’s own educational materials state Square does **not charge an additional dispute fee** for disputes/chargebacks (beyond normal processing fees). citeturn30search9 Country/processing availability is more limited than Stripe/PayPal; Square card processing is currently available in a fixed set of countries, including the US. citeturn13search1

### Helcim

Helcim is attractive for small organizations focused on lowering costs and avoiding monthly SaaS fees, while still having APIs and webhooks. Helcim advertises **no monthly fees**, and ACH pricing is published as **0.5% + $0.25, capped at $6** (for transactions up to $25,000). citeturn26view0 Card pricing is **interchange-plus** rather than a single flat rate, which can be cheaper than flat-rate processors at the cost of predictability; Helcim publishes margins by volume tiers (example shown for in-person as “Interchange+ 0.40% + 8¢” at $0–$50k monthly volume, plus interchange). citeturn26view0turn3search1 Helcim’s developer docs emphasize APIs and webhooks; its Payment API **requires idempotency keys** (keys cleared after 5 minutes) and provides detailed webhook signature verification: `webhook-signature` generated via HMAC-SHA-256 over `${webhook_id}.${webhook_timestamp}.${body}` using a base64-decoded verifier token; retries continue on a documented schedule for up to about **10 hours**. citeturn29search0turn20view0 Deposit timing is documented in Helcim’s help: credit cards typically **1–2 business days after batch settlement**, and ACH typically **3–4 business days after settlement**. citeturn6search7 Limitations: Helcim is positioned for US/Canada merchants (its own docs describe serving businesses across Canada and the US), and ACH collection is country-specific (US merchants can collect only from US bank accounts). citeturn14search5turn14search3 Also, Helcim notes PCI SAQ type can increase (e.g., some API/full-card-number integrations may push you into SAQ A‑EP or SAQ D), so you should prefer hosted/tokenized client-side options. citeturn10search4turn10search1

### Authorize.Net

Authorize.Net (a Visa solution) is a mature gateway that remains widely used in nonprofits and membership orgs, but it is less “developer-native” than Stripe. Its pricing page publishes an “All-in-one” plan at **$25/month** and **2.9% + $0.30 per transaction** (subject to eligibility), and a “Gateway + eCheck” plan that includes **eCheck at 0.75%** with a $25 monthly fee. citeturn1search5 It supports webhooks (HMAC-SHA512 in `X-ANET-Signature`, up to 10 retries) and a tokenization suite (“Accept”) including Accept.js and hosted forms that can keep you at **SAQ A** when using Authorize.Net-hosted UI. citeturn3search3turn18search1 It also supports Automated Recurring Billing (ARB) for subscriptions, including payment cards and eCheck.Net, and positions ARB as not requiring merchants to store sensitive payment data. citeturn24search0turn24search4 Settlement is batch-based; Authorize.Net batches captured transactions daily after cut-off, then your processor deposits funds typically within **48–72 business hours** (timing depends on your Merchant Service Provider). citeturn5search1turn5search8 For eCheck, funding can be materially slower; Authorize.Net’s support describes a multi-day holding process and notes it can take **7 business days** to process and deposit after settlement completes. citeturn5search4 Limitation: Authorize.Net requires a merchant account/MSP based in the US or Canada for gateway usage, and its API is not REST (XML with JSON translation), which can increase integration friction compared with Stripe/Square. citeturn12search6turn28search0

## Comparison table of processor attributes

The table below is tailored to Bloominglabs’ priorities: programmatic access and correctness under retries/out-of-order delivery; low PCI scope; recurring support; ACH availability; payout timing; and pricing predictability.

| Processor | API docs | Webhook signature & idempotency | SDK ecosystem | PCI scope strategy | Recurring/subscriptions support | Disputes/chargebacks | Payout timing | Pricing model | Merchant geo coverage |
|---|---|---|---|---|---|---|---|---|---|
| Stripe | Stripe Webhooks + PaymentIntents docs citeturn23search0turn29search1 | `Stripe-Signature`; retries up to **3 days**; duplicates possible; **event order not guaranteed** → must dedupe by event ID and/or object IDs citeturn23search0turn16search4 | Broad official libs; PaymentIntents guidance emphasizes idempotency keys citeturn29search1turn29search5 | Stripe is PCI Service Provider Level 1; use Checkout/Elements/Payment Element to avoid handling PAN citeturn11search0turn11search3 | Stripe Billing exists but adds **0.7% Billing volume**; you can implement recurring yourself with SetupIntent + off-session PaymentIntent citeturn17view0turn29search1 | Disputes supported; Stripe records and notifies via webhooks/API; typical dispute fee is $15 (US) citeturn30search2turn30search0 | Initial payout typically **7–14 days** after first payment; then per payout schedule citeturn16search1turn16search6 | Flat-rate for cards; ACH percentage w/cap citeturn16search0turn16search2turn16search3 | Stripe supported in many countries; US supported citeturn12search4 |
| PayPal Braintree | Braintree Direct overview + ACH docs citeturn15search3turn7search5 | Signed `bt_signature`/`bt_payload`; delivery may not be sequential; retries hourly up to **24h** (prod) citeturn2search5turn2search4 | Multiple server SDKs documented across languages citeturn2search6 | Braintree stores payment methods in its Vault; still requires annual SAQ; provides PCI guidance citeturn19search0turn19search1 | Recurring supported via vaulting + subscriptions; ACH supported for eligible merchants but not via Drop-in UI (custom JS v3) citeturn7search5turn7search6 | Chargeback fee published at **$15**; some disputes are PayPal-governed depending on method citeturn8search0turn8search5 | Credit cards “typically” deposit **2–5 business days after settlement**; ACH described as ~**5 business days** citeturn9search3turn9search5 | Published fee table, incl. charity rate citeturn8search0 | Merchants domiciled in US/CA/AU/EU/SG/HK/MY/NZ citeturn15search3 |
| Square | Web Payments SDK + Subscriptions docs citeturn10search2turn25search0 | HMAC-SHA256 via `x-square-hmacsha256-signature`; `event_id` supports dedupe; retries exponential up to **24h** citeturn2search0turn2search1 | Official SDK utilities for webhook verification citeturn2search0 | Web Payments SDK provides **PCI-compliant inputs** and tokenization on client side citeturn10search2turn10search5 | Subscriptions API exists; but **ACH not available through Subscriptions API** (no bank account stored-on-file) citeturn25search7turn25search0 | Square states **no additional dispute fee** for disputes citeturn30search9 | Standard **next-business-day** transfers; instant/same-day options with fee citeturn6search0 | Flat-rate cards; ACH fee with min/cap citeturn1search1turn1search0 | Card processing available in a limited set of countries incl. US citeturn13search1 |
| Helcim | Helcim API overview + webhooks + idempotency citeturn28search1turn20view0turn29search0 | Webhook HMAC-SHA256 (`webhook-signature`, `webhook-timestamp`, `webhook-id`); retry schedule up to ~10 hours citeturn20view0 | Helcim advertises APIs + webhooks; official devdocs exist citeturn7search0turn28search1 | PCI SAQ depends on integration; Helcim documents SAQ A/SAQ A‑EP/SAQ D considerations citeturn10search4turn10search1 | Recurring API exists; Helcim pricing lists recurring payments as **+0.4% per transaction** (if using their recurring tool) citeturn24search2turn26view0 | Chargeback fee shown on pricing page ($15 if lost); ACH returns fee $5 citeturn26view0 | Credit card deposits typically **1–2 business days** after batch; ACH **3–4 business days** after settlement citeturn6search7 | Interchange-plus (variable) + published ACH pricing citeturn26view0turn3search1 | Oriented to US/Canada; ACH is country-specific citeturn14search5turn14search3 |
| Authorize.Net | API reference + webhooks + Accept suite citeturn28search0turn3search3turn18search1 | Webhook `X-ANET-Signature` (HMAC-SHA512); retries up to 10 times citeturn3search3 | SDKs/sample code referenced; API is XML/JSON-translation citeturn24search0turn28search0 | Accept Hosted / Accept.js-with-UI can keep **SAQ A**; Accept.js alone is SAQ A‑EP citeturn18search0turn18search1 | ARB supports recurring cards and eCheck.Net citeturn24search0turn24search4 | Chargeback fees often MSP-dependent (not uniformly published in Authorize.Net plan page) | Batches daily; deposits typically **48–72 business hours** (processor/MSP dependent); eCheck can take **7 business days** citeturn5search1turn5search4 | Monthly gateway fee + per-transaction fees; eCheck rate published citeturn1search5 | Requires MSP/merchant account based in US/Canada for gateway citeturn12search6 |

## Codex-ready implementation spec for dues payments and processor integration

This spec assumes: Django/Postgres modular monolith; dues are monthly; Full $50 / Hardship $25 are configurable; prepayments/credits tracked; door access and bank import are adapters; Every.org remains donations-only.

### Core design principles for the payment layer

Your payment processor integration must follow a strict philosophy:

The **Bloominglabs core is the ledger of record**, not Stripe/Square/etc. Processor objects are references and reconciliation sources.

Your system records three distinct concepts (never collapse them):
- **Charges**: what Bloominglabs says is owed (dues invoice lines, ad-hoc invoices).
- **Payments (cash receipts)**: money actually received, with processor references.
- **Allocations**: how money is applied to charges vs held as member credit.

This separation is required to correctly model prepayments, arrears, partial payments, refunds, and “cash basis vs earned dues” reporting.

### Minimal data model for payment processing

Implement the following models (names are suggestions; Codex can adjust naming but must preserve semantics and invariants).

**ProcessorCustomer**
- `id`
- `processor` enum (`STRIPE`, `SQUARE`, `BRAINTREE`, `HELCIM`, `AUTHORIZE_NET`)
- `processor_customer_id` (string)
- `client_id` (FK to `Client`)
- unique constraint: (`processor`, `processor_customer_id`)

**ProcessorPaymentMethod**
- `id`
- `processor`
- `processor_payment_method_id`
- `client_id`
- `member_id` nullable
- `method_type` (card, ach, wallet)
- `fingerprint_hash` nullable
- `is_default`
- `created_at`

**Payment**
- `id`
- `client_id`
- `member_id` nullable
- `received_at` (timestamp)
- `amount_cents`, `currency`
- `source_type` enum:
  - `DUES_PAYMENT`
  - `PREPAYMENT_TOPUP`
  - `ARREARS_CATCHUP`
  - `DONATION` (for completeness—even if chiefly via Every.org)
  - `OTHER_INCOME`
- `processor` nullable
- `processor_payment_id` (PaymentIntent/Charge/etc)
- `processor_balance_txn_id` nullable (for reconciliation)
- `status` enum (`PENDING`, `SUCCEEDED`, `FAILED`, `REFUNDED`, `REVERSED`)
- unique constraint for idempotency: (`processor`, `processor_payment_id`) where present

**Invoice / Charge**
- `invoice_number`
- `client_id`
- `member_id` nullable
- `issue_date`, `due_date`
- `status` (`ISSUED`, `PARTIAL`, `PAID`, `VOID`, `OVERDUE`)
- `service_period_start`, `service_period_end`
- line items include `DUES` lines, etc.

**Allocation**
- `payment_id`
- `invoice_id`
- `allocated_cents`
- rule: sum(allocations.payment_id) ≤ payment.amount_cents
- rule: invoice.paid_amount = sum(allocations.invoice_id)

**MemberBalanceSnapshot** (optional optimization; correctness derives from allocations)
- `member_id`
- `as_of`
- `credit_cents`
- `receivable_cents`

**WebhookEvent**
- `processor`
- `event_id` (Stripe: `evt_...`; Square: `event_id`; Helcim: `webhook-id`; Braintree: you may synthesize from payload fields if no unique ID is present)
- `received_at`
- `payload_json` (raw, stored)
- `signature_valid` (bool)
- unique constraint: (`processor`, `event_id`)

### Webhook handling patterns

These patterns are mandatory for correctness because processors retry (and can deliver out-of-order).

#### Idempotency and ordering

For Stripe, you must assume:
- retries for up to **3 days**, duplicates possible citeturn16search4turn23search0
- event ordering not guaranteed citeturn23search0

For Square:
- events can be sent more than once (use `event_id` for idempotency) citeturn2search1turn25search5

For Helcim:
- implement idempotency on outbound Payment API calls using required idempotency keys citeturn29search0
- verify webhooks via their HMAC scheme and dedupe by `webhook-id` citeturn20view0

For Authorize.Net:
- verify `X-ANET-Signature` HMAC-SHA512; retries up to 10 times citeturn3search3

For Braintree:
- parse signed payload; webhooks may not be sequential; retries up to 24h citeturn2search5turn2search4

**Codex rule:** webhook handlers must be **idempotent, order-independent**, and should be designed as “record → enqueue → reconcile.”

#### Security requirements

- Require HTTPS for all webhook endpoints (processors assume public endpoints).
- Verify signatures using the processor’s recommended approach:
  - Stripe: verify `Stripe-Signature` against endpoint signing secret (raw body). citeturn23search0
  - Square: verify `x-square-hmacsha256-signature` using signature key + notification URL + raw body. citeturn2search0
  - Helcim: verify `webhook-signature` HMAC-SHA256 over `${webhook_id}.${webhook_timestamp}.${body}` with base64-decoded verifier token. citeturn20view0
  - Authorize.Net: verify `X-ANET-Signature` HMAC-SHA512 using Signature Key + body. citeturn3search3
  - PayPal (if used for direct PayPal webhooks): PayPal provides an API endpoint to verify signatures using transmission headers + cert URL. citeturn4search0

- Reject requests with invalid signatures; log them with `signature_valid=false` for audit (do not process).

#### Retry handling and internal queues

Webhook endpoint must:
- Return HTTP 2xx quickly after verification + persistence to avoid downstream retries (Stripe retries up to days; Square up to 24h; Helcim has its own schedule). citeturn23search0turn2search1turn20view0
- Enqueue a background job `process_webhook_event(processor, event_id)`.

### Sample REST endpoints for dues payments

These endpoints are designed for the **recommended Stripe-first** build. Other processors should conform to the same internal abstractions.

**Create a dues payment session (one-time)**
- `POST /api/payments/stripe/checkout-session`
- Body:
  - `member_id`
  - `purpose` enum: `PAY_OUTSTANDING`, `TOP_UP_CREDIT`
  - `amount_cents` (required for TOP_UP_CREDIT; ignored for PAY_OUTSTANDING)
- Behavior:
  - compute how much is owed if `PAY_OUTSTANDING` (optionally cap to include prepaid credits)
  - create Stripe Checkout Session with metadata:
    - `member_id`, `client_id`, `invoice_ids` (if paying specific invoices), `purpose`
  - use Stripe idempotency keys on session creation to prevent duplicates. citeturn29search5

**Enroll autopay**
- `POST /api/payments/stripe/setup-intent`
- Behavior:
  - create SetupIntent for member; return `client_secret` for frontend
  - on webhook confirmation, attach payment method and mark as default

**Webhook endpoints**
- `POST /webhooks/stripe`
- `POST /webhooks/square` (future optional)
- `POST /webhooks/helcim` (future optional)
- `POST /webhooks/braintree` (future optional)
- `POST /webhooks/authorize-net` (future optional)

### Event flows

#### Stripe one-time payment for dues / prepayment

```mermaid
sequenceDiagram
  participant Member
  participant Core as Bloominglabs Core (Django)
  participant Stripe

  Member->>Core: POST /api/payments/stripe/checkout-session (purpose=TOP_UP_CREDIT or PAY_OUTSTANDING)
  Core->>Stripe: Create Checkout Session (Idempotency-Key)
  Stripe-->>Member: Redirect to hosted Checkout
  Member->>Stripe: Completes payment (card or ACH)
  Stripe-->>Core: webhook event (e.g., checkout.session.completed; payment_intent.succeeded)
  Core->>Core: Verify signature, persist WebhookEvent, enqueue process job
  Core->>Stripe: Retrieve latest objects by IDs (defensive against out-of-order events)
  Core->>Core: Create Payment + Allocation(s); update member credit/debt and membership status
  Core-->>Member: Receipt/portal update
```

Design notes:
- Stripe explicitly warns events may be out of order, so reconciliation must “pull latest object state by ID” when needed. citeturn23search0
- Stripe retries webhook delivery for up to three days; hence, `WebhookEvent(processor,event_id)` uniqueness is essential. citeturn16search4turn23search0

#### Stripe autopay enrollment + monthly charge job

```mermaid
sequenceDiagram
  participant Member
  participant Core as Bloominglabs Core (Django)
  participant Stripe
  participant Scheduler as Monthly Scheduler (Celery beat)

  Member->>Core: POST /api/payments/stripe/setup-intent
  Core->>Stripe: Create SetupIntent
  Member->>Stripe: Confirms payment method in UI
  Stripe-->>Core: setup_intent.succeeded / payment_method.attached webhook
  Core->>Core: Verify + persist event; store default payment method

  Scheduler->>Core: Run monthly dues generation job (default 1st)
  Core->>Core: Create dues invoices for active members
  Core->>Stripe: Create off_session PaymentIntent for members with autopay enabled (Idempotency-Key)
  Stripe-->>Core: payment_intent.succeeded / failed webhook
  Core->>Core: Allocate payment to invoices; update status (ACTIVE / PAST_DUE)
```

### Reconciliation and reporting flows

A “payment succeeded” webhook is not your only reconciliation input. For finance reports and bank reconciliation, you should also periodically pull “clearing” data (payouts/balance transactions) so your books match deposits.

```mermaid
flowchart LR
  subgraph External
    StripeBalance[Stripe balance txns / payouts]
    BankCSV[Bank exports (CSV initially)]
  end

  subgraph Core[Django/Postgres Core Ledger]
    Payments[Payments + Allocations]
    Journal[Journal Entries]
    Reports[Financial Report Generator]
  end

  StripeBalance -->|daily sync job| Journal
  Payments --> Journal
  BankCSV -->|import adapter| Journal
  Journal --> Reports
```

Stripe payout scheduling and initial payout behavior are documented and should be surfaced in your finance UI so treasurers understand timing differences. citeturn16search1turn16search6

### TDD requirements for processor integration

Codex must implement the payment integration with test-first rigor. Minimum test inventory (Stripe-first, but patterns generalize):

**Pure unit tests**
- `compute_outstanding(member, as_of)` with cases:
  - prepaid credit covers current month
  - partial payment → remaining due
  - arrears plus prepayment in same payment
- `allocate_payment_fifo(payment, invoices)` invariants:
  - allocations never exceed payment amount
  - invoice paid amount never exceeds invoice total
- `render_financial_report(from,to)` returns both:
  - earned dues (invoiced & paid for service period)
  - cash basis intake
  - difference breakdown by `source_type`

**Webhook ingestion tests**
- signature verification:
  - valid signature accepted, invalid rejected (Stripe `Stripe-Signature`). citeturn23search0
- idempotency:
  - same `event_id` delivered twice produces exactly one Payment
- out-of-order:
  - `invoice.paid` received before `invoice.created` equivalent scenario: handler fetches missing referenced objects and still reaches correct state (Stripe explicitly warns about ordering). citeturn23search0

**Integration tests**
- Stripe retries: simulate receiving same payload twice, ensure dedupe.
- Failure paths:
  - PaymentIntent succeeds then later ACH return/dispute → system reverses and adjusts member access state (Stripe ACH can fail after initial success; Stripe docs describe failures/disputes and balance removal). citeturn0search1turn0search0

**Property/invariant tests (high value)**
- journal entries always balance to zero (if implementing double-entry layer)
- member balance computed from events equals stored snapshot

## Migration notes from FreshBooks to new ledger

### What FreshBooks can export

FreshBooks support documents that you can export data to **CSV and PDF**, including: Chart of Accounts, Clients, Expenses, Invoices, Items/Services, Vendors, and Reports. citeturn21search0turn21search3 This is sufficient for a one-time cutover migration.

### Recommended export set and mapping

Export these FreshBooks datasets:

- **Clients CSV** → map to `Client` (your “client superset” model matches FreshBooks’ concept of clients). citeturn21search0turn21search6  
- **Invoices CSV** → map to `Invoice` + `InvoiceLine`. citeturn21search0turn21search4  
- **Expenses CSV** → map to `Expense` (or `BankTransaction` + categorization). citeturn21search0turn21search2  
- **Chart of Accounts CSV** → map to your internal `Account` (GL), preserving names/codes where sensible. citeturn21search0  
- **Reports exports** (Profit/Loss equivalent; A/R aging; etc.) → use as migration validation baselines (“new system totals match old system totals per period”). citeturn21search3

### Ledger mapping rules

To preserve audit trails, do not “rewrite the past” into newly invented invoices unless necessary. Preferred approach:

- Import historical invoices/payments as **read-only historical records** (flag `import_batch_id`).
- For balances-at-cutover:
  - compute each member’s net **receivable** and **prepaid credit** at cutoff date
  - create a single “Opening Balance” journal entry per member (or per client) that sets A/R and prepaid liability correctly.

If needed, FreshBooks also has webhooks and signatures, but since Bloominglabs wants to eliminate FreshBooks as a line item, you should treat FreshBooks as a migration-only source—not a continuing integration. citeturn21search1

## Accounting and export guidance to replace FreshBooks short-term

### Minimal viable bookkeeping exports from the new system

To replace FreshBooks “ledger function” quickly, implement these exports/reports early:

- **Cash receipts report (CSV)**: payments received by date, source_type, processor, net/gross if available.
- **Dues earned report (CSV)**: dues invoiced/earned per month + amounts paid for those service periods.
- **Member balances report**: credit, outstanding, days past due.
- **Category summary**: income categories and expense categories by period.
- **Reconciliation report**: Stripe payouts (or other processor deposits) vs bank transactions vs internal journal.

### Minimal double-entry mapping (recommended even if simple)

Even if you defer a full accounting UI, implement a minimal chart of accounts and auto-post journal entries:

- When an invoice is issued:  
  - Dr **Accounts Receivable**  
  - Cr **Dues Income** (or other income category)

- When cash is received as prepayment (no invoice allocation yet):  
  - Dr **Bank/Stripe Clearing**  
  - Cr **Member Prepayments (Liability)**

- When a payment is allocated to an invoice:  
  - Dr **Member Prepayments (Liability)** (if applied from credit) or Dr **Bank** (if direct)  
  - Cr **Accounts Receivable**

This is the simplest scheme that keeps “earned vs cash” reporting coherent.

### Open-source accounting tools to consider

These are optional; your Django system can be the ledger, but if you want a dedicated accounting UI for treasurers, these are realistic complements.

**GnuCash**: Mature desktop accounting with double-entry, reports, and strong bank import support. Official docs list import formats including **QIF, OFX/QFX, CSV** and others. citeturn22search3turn22search9turn22search5 Pros: robust, time-tested, good importing; Cons: not web/multi-user by default; integrating automated exports requires a workflow.

**Beancount**: Plain-text double-entry accounting “language” and tooling; the project describes itself as double-entry accounting from text files that can generate reports and provides a web interface. citeturn22search2 Pros: version-controlled, audit-friendly, excellent for reproducibility; Cons: steep learning curve for nontechnical treasurers; you likely still need a friendly UI layer (e.g., not in scope for v1).

**Akaunting**: Web-based open-source accounting that you can self-host; it emphasizes invoicing, bills, expense tracking, bank accounts, and reporting, and positions itself as installable on your server with privacy and control. citeturn22search0turn22search1turn22search6 Pros: web UI, self-hosted; Cons: adds another app to host and integrate; you may still prefer to keep the authoritative ledger in Django and push summary entries outward.

## Effort estimates, operational costs, and prioritized official sources

### Implementation effort and operational cost estimates

These are rough, engineering-planning estimates for Bloominglabs’ environment (Django/Postgres, TDD, ledger-owned-by-core). They exclude the broader membership UX, RFID integration, Slack automation, and bank-import adapters beyond CSV.

| Processor | Initial integration dev effort | Ongoing monthly fees | Per-transaction fees (typical) | Operational notes |
|---|---:|---:|---|---|
| Stripe (recommended) | ~40–90 hours | $0 (Payments); **Billing adds 0.7%** if used citeturn17view0turn16search0 | Cards: 2.9% + $0.30; ACH: 0.8% cap $5 citeturn16search0turn16search2 | Most mature webhook behavior docs; plan time for reconciliation job + out-of-order handling citeturn23search0 |
| PayPal Braintree | ~60–120 hours | Not publicly listed as monthly on fee page (assume $0 unless contract says otherwise) citeturn8search0 | Cards/wallet: 2.89% + $0.29 (std); charity 2.19% + $0.29; ACH: 0.75% cap $5 citeturn8search0 | More complexity (PayPal flows, BT payload parsing). Strong for PayPal/Venmo communities. |
| Square | ~60–120 hours | $0 for basic processing; optional paid plans exist (not required) citeturn1search0turn1search2 | Online API cards: 2.9% + $0.30; ACH via API: 1% min $1 cap $5 citeturn1search1 | Subscription ACH limitation impacts “ACH autopay dues” design citeturn25search7 |
| Helcim | ~60–140 hours | $0 monthly fees citeturn26view0 | Cards: interchange + margin; ACH: 0.5% + $0.25 cap $6; recurring tool +0.4%/txn citeturn26view0turn3search1 | Smaller ecosystem; great idempotency + webhook signature docs. Budget extra time for PCI SAQ determination. citeturn20view0turn10search4 |
| Authorize.Net | ~80–160 hours | $25/month plan fee citeturn1search5 | All-in-one: 2.9% + $0.30; eCheck 0.75% (plan-dependent) citeturn1search5 | Non-REST API adds friction; eCheck funding slower; MSP/merchant-account negotiation overhead citeturn5search4turn12search6 |

### Prioritized official sources appendix

The links below are provided as an implementation reading list for Codex and reviewers. (All are official documentation or official pricing pages.)

```text
Stripe
- Pricing (US): https://stripe.com/us/pricing
- ACH Direct Debit product/pricing: https://stripe.com/payments/ach-direct-debit
- ACH Direct Debit docs (timing, disputes): https://docs.stripe.com/payments/ach-debit
- Webhooks docs (retries, ordering, signature verification): https://docs.stripe.com/webhooks
- PaymentIntents API: https://docs.stripe.com/payments/payment-intents
- Idempotent requests: https://docs.stripe.com/api/idempotent_requests
- Payouts: https://docs.stripe.com/payouts
- Stripe Billing pricing (0.7% billing volume): https://stripe.com/billing/pricing
- Security / PCI Level 1 info: https://docs.stripe.com/security/stripe

PayPal Braintree
- Fees & pricing (US): https://www.paypal.com/us/enterprise/paypal-braintree-fees
- Braintree Direct overview + availability: https://developer.paypal.com/docs/bt-direct-overview/
- Get paid (funding timelines): https://developer.paypal.com/braintree/articles/get-started/get-paid/
- ACH Direct Debit overview: https://developer.paypal.com/braintree/docs/guides/ach/overview
- ACH settlement/funding timeline: https://developer.paypal.com/braintree/articles/guides/payment-methods/ach/
- Webhook parsing (+ retries): https://developer.paypal.com/braintree/docs/guides/webhooks/parse/
- PCI compliance overview: https://developer.paypal.com/braintree/articles/risk-and-security/compliance/pci-compliance/

Square
- Pricing & processing fees: https://squareup.com/us/en/pricing
- Fees explainer (incl. Online API, ACH via API): https://squareup.com/payments/our-fees
- Webhooks overview (idempotency/event_id, retries): https://developer.squareup.com/docs/webhooks/overview
- Webhook signature validation: https://developer.squareup.com/docs/webhooks/step3validate
- Web Payments SDK (PCI-compliant inputs; ACH, wallets): https://developer.squareup.com/reference/sdks/web/payments
- Subscriptions API reference: https://developer.squareup.com/reference/square/subscriptions-api
- Subscription billing limitation (no ACH in Subscriptions API): https://developer.squareup.com/docs/subscriptions-api/subscription-billing
- Deposit schedule (US): https://squareup.com/help/us/en/article/5438-next-business-day-deposit-schedule
- Disputes/chargebacks (Square says no dispute fee): https://squareup.com/us/en/the-bottom-line/managing-your-finances/what-is-a-chargeback-what-makes-it-happen

Helcim
- Pricing (ACH pricing, no monthly fees, recurring add-on): https://www.helcim.com/pricing/
- Developer API overview: https://www.helcim.com/developer-api/
- API docs overview: https://devdocs.helcim.com/docs/overview-of-helcim-api
- Webhooks (signature verification + retry schedule): https://devdocs.helcim.com/docs/webhooks
- Payment API idempotency: https://devdocs.helcim.com/docs/idempotency
- Deposit timelines: https://learn.helcim.com/docs/bank-deposit-timelines-helcim
- PCI SAQ guidance: https://learn.helcim.com/docs/manual-pci-compliance

Authorize.Net
- Pricing: https://www.authorize.net/solutions/merchantsolutions/pricing/
- API reference index: https://developer.authorize.net/api/reference/index.html
- Webhooks feature: https://developer.authorize.net/api/reference/features/webhooks.html
- Accept.js (SAQ A vs A-EP options): https://developer.authorize.net/api/reference/features/acceptjs.html
- Recurring billing API (ARB): https://developer.authorize.net/api/reference/features/recurring-billing.html

FreshBooks (migration/export)
- Export data overview: https://support.freshbooks.com/hc/en-us/articles/360032628152-How-do-I-export-my-data
- Export reports: https://support.freshbooks.com/hc/en-us/articles/227478548-How-do-I-export-my-reports
- FreshBooks webhooks (if needed for transitional sync only): https://www.freshbooks.com/api/webhooks

Open-source accounting tools (evaluation)
- GnuCash imports (CSV/OFX/QFX): https://gnucash.org/docs/v5/C/gnucash-guide/importing-from-files.html
- Beancount repository: https://github.com/beancount/beancount
- Akaunting open-source overview: https://akaunting.com/open-source-accounting-software
```

