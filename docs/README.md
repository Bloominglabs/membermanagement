# Documentation Guide

Use this file as the entry point for the repository documentation set.

## Current Authority

These are the current project documents and should win when they conflict with older material:

- [`spec.md`](./spec.md): current product and integration spec
- [`architecture.md`](./architecture.md): implemented architecture and known gaps
- [`admin-ui.md`](./admin-ui.md): intended staff workflow surface
- [`qa-hosting.md`](./qa-hosting.md): current deployment recommendation
- [`adr/`](./adr/): decision trail for implemented features and follow-up reviews

## Reference Material

These documents are useful context, but they are not the current source of truth:

- [`CULMINATION_SPEC.md`](./CULMINATION_SPEC.md): earlier implementation-oriented system spec
- [`membermanagement-deep-research-report.md`](./membermanagement-deep-research-report.md): research synthesis and background analysis

The deep research report intentionally remains a reference memo and may retain research-era source markers and exploratory detail that should not override the current spec or ADRs.

## Historical Material

These documents describe prior directions and are retained only for historical context:

- [`DEVELOPMENT_PLAN.md`](./DEVELOPMENT_PLAN.md): Google Sheets and PayPal prototype handoff

The historical Google Sheets plan is not authoritative for the Django/Postgres system and should not be used to make current implementation decisions.
