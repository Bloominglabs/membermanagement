# ADR 0010: Project Standards Alignment

## Status

Accepted

## Context

The repository-level working practices now live in `AGENTS.md` and require a documentation spine, explicit fast and extended test paths, coverage documentation when total coverage is not yet enforced, and current entrypoint documentation. The rewrite branch currently has a passing default Node test suite, but the review found several standards gaps:

- `README.md` still points at the deleted `development-practices.md` file.
- `LOG.md`, `MEMORY.md`, `LESSONS.md`, and `docs/log/` do not exist yet.
- `package.json` has only one `test` script, so the required fast and extended test paths are not explicit.
- Node v22.22.2 executes the suite successfully under `--experimental-test-coverage`, but the coverage reporter exits nonzero while printing the coverage report.

## Decision

This standards-alignment slice will add repository standards tests before changing the affected documentation and scripts. The implementation will:

- make `AGENTS.md` the active practice entrypoint from `README.md`
- add the required documentation-layer files with current scope and known gaps
- add explicit `test:fast`, `test:extended`, and `test:coverage` scripts while keeping `npm test` on the fast path
- document the current coverage-tooling exception and feature-surface gaps rather than claiming total coverage
- add transfer-oriented source comments across the active tracked JavaScript files
- record this review and the resulting next steps in `LOG.md`

No runtime behavior is intentionally changed by this ADR.

## Consequences

### Positive

- Future review work has a chronological log and stable process entrypoints.
- The test commands advertise the expected fast and extended paths even before slower regressions exist.
- Coverage limitations are explicit and revisitable instead of implicit.

### Negative

- The extended test command is initially a reserved lane; it will not provide additional behavioral confidence until a future ADR adds genuinely slow tests.
- Coverage remains documented rather than enforced until the Node coverage reporter issue is resolved or a separate coverage tool is adopted.

## Success Criteria

- A standards test fails before these repository files and scripts are added, then passes afterward.
- `npm test`, `npm run test:fast`, and `npm run test:extended` pass.
- The README points to the active practices file and current documentation layers.
- `LOG.md` records the review, verification commands, coverage exception, and next steps.
- Active tracked JavaScript source files contain comments that explain module boundaries, rationale, or transfer knowledge.
