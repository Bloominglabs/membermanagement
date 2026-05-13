# Coverage Status

## Current Position

The repository has a passing behavioral test suite, but total coverage is not yet enforced.

On 2026-05-13, `node --test --experimental-test-coverage` and `node --test --experimental-test-coverage --test-reporter=spec` both executed the full suite successfully under Node v22.22.2, then exited nonzero while the Node test runner attempted to print coverage output. Because the reporter failed, no trustworthy coverage percentage was accepted for this review.

## Rationale For Exception

The active codebase is still a rewrite branch with intentionally incomplete feature surface compared with the legacy Django system. The current suite exercises the implemented engine workflows, HTTP routes, runtime bootstrapping, persistence adapters, session lifecycle, and password hashing, but the project should not claim total coverage until coverage reporting is reliable and the rebuilt feature surface is broader.

## Required Follow-Up

- Re-test built-in coverage after changing or pinning the Node version.
- If built-in coverage remains unreliable, add a dedicated coverage tool and define thresholds that match the total-coverage standard or document any remaining exclusions.
- Revisit this file whenever a new ADR adds runtime behavior, persistence shape, or interface surface.
