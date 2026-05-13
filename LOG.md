# Development Log

This file is the chronological spine for project work. Longer notes live under `docs/log/` and are linked from dated entries here.

## 2026-05-13

- Reviewed the rewrite branch against `AGENTS.md` standards under ADR 0010.
- Verified the baseline default suite with `npm test`: 24 tests passed, with no skipped or todo tests.
- Confirmed `node --test --experimental-test-coverage` executes the tests but exits nonzero under Node v22.22.2 while printing the built-in coverage report; documented that exception in `docs/coverage.md`.
- Added standards coverage in `spec/project-standards.test.js`. The test failed first for missing documentation layers, missing explicit test scripts, and missing ADR 0010 AAR, then passed after remediation.
- Updated the README and architecture map so current entrypoints point to `AGENTS.md`, `LOG.md`, and the ADR sequence.
- Added transfer-oriented source comments across the active tracked JavaScript source files.
- Verified `npm test`, `npm run test:fast`, `npm run test:extended`, and `node --check frontend/admin/app.js` after remediation. The fast paths ran 27 tests successfully; the extended lane is present but currently has no dedicated extended tests.
- Re-ran `npm run test:coverage`; all 27 tests passed, then Node v22.22.2 exited nonzero while generating coverage output.
- Detailed review notes and next steps: `docs/log/2026-05-13-project-review.md`.
