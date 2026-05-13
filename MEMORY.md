# Project Memory

## Current high-priority facts

- The active rewrite branch is `adr-0006-engine-static-admin-rewrite`.
- The tracked source is the JavaScript rewrite under `src/`, `spec/`, `frontend/admin/`, and `docs/`. The ignored `backend/`, `onprem/`, and `tests/` directories are local legacy artifacts, not active rewrite source.
- `npm test` is the default fast path and delegates to `npm run test:fast`.
- `npm run test:extended` is reserved for slower regressions. It currently has no dedicated extended tests.
- Coverage is documented in `docs/coverage.md`; it is not yet enforced because Node v22.22.2 fails while printing built-in coverage output in this environment.
