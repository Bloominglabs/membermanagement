# Lessons Learned

## Durable lessons

- Keep public entrypoint docs synchronized with active repository instructions; stale process-file links can obscure real working practices.
- Treat coverage tooling as part of the verification surface. A passing test suite is not a coverage claim when the coverage reporter itself fails.
- Reserve a separate extended test lane before slow tests are needed so future regressions have an obvious home outside the default fast path.
