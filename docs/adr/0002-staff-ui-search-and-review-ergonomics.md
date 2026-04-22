# ADR 0002: Staff UI Search and Review Ergonomics

## Status

Accepted

## Context

The current Staff UI covers the major workflow areas, but it still falls short of the documented admin UI plan in several practical ways:

- there is no global search route across members, clients, invoices, payments, and RFID credentials
- list pages have filters, but limited sort and date-range support
- several review screens do not provide the direct raw-admin, workspace, or API escape hatches promised in the UI plan

These gaps do not block the backend, but they force staff back into Django admin for routine investigation and make the custom workflow layer less useful than intended.

## Decision

Implement the next UI parity slice with three goals:

1. add a stable staff-global search page
2. improve review lists with sort order and date-range controls where the plan expects them
3. add direct raw-admin, workspace, and API links on the relevant staff review screens

The implementation remains server-rendered and backend-authoritative.

## Consequences

### Positive

- staff gain one obvious route for cross-object lookup
- billing review pages become faster to scan and less dependent on raw admin navigation
- the Staff UI better matches the documented promise without introducing SPA complexity

### Negative

- templates and views gain more branching for list-state handling
- search remains intentionally shallow and operational rather than a full-text subsystem

## Success Criteria

- `/staff/search/` returns cross-entity results
- member, invoice, and payment review screens accept explicit sort controls
- invoice and payment review screens accept date-range filters
- review screens expose direct admin and useful API/workspace links
