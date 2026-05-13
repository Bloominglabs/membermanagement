# 2026-05-13 Project Review

## Scope

This review covered the tracked JavaScript rewrite branch. Ignored legacy Django artifacts, local virtual environments, generated caches, and installed dependencies were not treated as active rewrite source.

## Baseline Findings

- The default Node test suite passed before changes: 24 passing tests, no skipped tests, no todo tests.
- Repository practices had moved into `AGENTS.md`, but `README.md` still linked to the deleted `development-practices.md` file.
- The required documentation layers did not exist yet: `LOG.md`, `MEMORY.md`, `LESSONS.md`, and `docs/log/`.
- `docs/architecture.md` described layers and follow-on work but did not map the implemented design to the ADR sequence.
- `package.json` exposed only a single `test` script; there was no explicit fast or extended suite command.
- Built-in Node coverage reporting was attempted with Node v22.22.2. The tests passed, but the coverage reporter exited nonzero while printing the report.

## Remediation

- ADR 0010 was added before implementation work.
- `spec/project-standards.test.js` was added and run red before the repository standards files and package scripts were changed.
- `README.md` now points at `AGENTS.md`, `LOG.md`, and `docs/coverage.md`.
- `LOG.md`, `MEMORY.md`, `LESSONS.md`, `docs/coverage.md`, and this detailed log note were added.
- `docs/architecture.md` now maps ADR 0006 through ADR 0010 to the current design.
- `package.json` now exposes `test:fast`, `test:extended`, and `test:coverage`, with `npm test` mapped to the fast suite.
- Transfer-oriented source comments were added across the active tracked JavaScript source files.

## Verification

- `node --test spec/project-standards.test.js` failed before remediation for missing documentation layers, missing script split, and missing ADR 0010 AAR.
- `node --test spec/project-standards.test.js` passed after remediation: 3 tests passed.
- `npm test` passed after remediation: 27 tests passed.
- `npm run test:fast` passed after remediation: 27 tests passed.
- `npm run test:extended` passed after remediation. It currently selects no named extended tests and therefore reports file-level harness passes only.
- `node --check frontend/admin/app.js` passed after source-comment updates.
- `npm run test:coverage` executed 27 passing tests, then Node v22.22.2 exited nonzero while printing coverage output with `TypeError: String.prototype.split called on null or undefined`.

## Next Steps

- Add genuinely slow tests to the extended suite when future features introduce database, integration, or migration regressions that should not run on the default fast path.
- Decide whether to pin a Node version with reliable built-in coverage or add a dedicated coverage tool and threshold.
- Add scheduled cleanup for expired sessions, as already identified by ADR 0009 and deployment notes.
- Reintroduce Stripe and Every.org provider adapters behind the existing provider-port direction.
- Expand role policy beyond `staff-admin` and `member-self` after the required workflows are stable.
- Continue rebuilding write paths for expenses, exports, access control, and reconciliation.
