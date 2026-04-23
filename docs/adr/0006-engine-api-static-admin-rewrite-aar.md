# AAR 0006: Engine, API, and Static Admin Rewrite

## Outcome

ADR 0006 succeeded. The rewrite now has:

- a clean orphan branch distinct from the legacy monolith
- a core engine that owns auth, authz, and workflow entry points
- a thin HTTP adapter
- a static admin client that authenticates against the API instead of relying on server-side template sessions

## What Worked

- Starting from a clean branch prevented accidental coupling back to the Django stack.
- Repository ports made it straightforward to add a second persistence adapter in ADR 0007.
- Cross-origin token-based auth fits the intended static-hosted frontend deployment model.

## What Remains

- Durable database adapters beyond the interim JSON-file store
- third-party provider adapters for Stripe and Every.org
- broader operational coverage across expenses, access control, exports, and reports

