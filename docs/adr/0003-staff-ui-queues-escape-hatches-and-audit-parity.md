# ADR 0003: Staff UI Queues, Escape Hatches, and Audit Parity

## Status

Accepted

## Context

The Staff UI now covers search and the primary billing review surfaces, but several documented promises still remain incomplete:

- staff home and review pages do not expose stable queue links for the most common operational slices
- donations, access, and expenses lack the same direct admin, API, and audit escape hatches already added to billing review
- invoice review still requires repetitive row-by-row issue and void operations
- the audit timeline does not yet support `entity_id` or date-range filtering, and it shows only a narrow summary of each change

These are still UI gaps rather than backend-authority gaps, but they directly affect the day-to-day usefulness of the staff workflow layer.

## Decision

Implement the next Staff UI parity slice with four bounded changes:

1. add stable queue links for common member, billing, and expense review slices
2. extend direct admin, API, and audit escape hatches to the remaining staff workflow pages
3. add a bounded bulk invoice action for issue and void operations
4. extend the audit timeline with `entity_id`, date-range filters, entity links, and concise change summaries

The implementation remains thin and server-rendered, and every write path continues to terminate in existing backend services.

## Consequences

### Positive

- staff gain one-click routes to the queues they actually use repeatedly
- support pages become consistent with the escape-hatch model defined in the admin UI plan
- repetitive invoice handling no longer requires one form submission per record
- the audit page becomes materially more useful for investigations

### Negative

- staff views and templates gain more list-state and link-generation code
- queue links intentionally encode a small opinionated set of defaults, which must stay aligned with operations

## Success Criteria

- home and review pages expose stable queue links for common member, billing, and expense workflows
- donations, access, and expense pages expose relevant admin, API, and audit links
- invoice review supports bulk issue and void actions
- audit timeline filters by `entity_type`, `entity_id`, and date range, and shows direct entity links plus change summaries
