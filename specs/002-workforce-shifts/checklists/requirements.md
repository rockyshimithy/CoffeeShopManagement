# Specification Quality Checklist: M1 Workforce: Shifts Inside Store Scope

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-26
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Items marked incomplete require spec updates before `/speckit.clarify` or `/speckit.plan`.
- Validation run 1: all items pass.
- FR-022 and SC-005 mention a stored copy of the schedule because the project
  constitution makes the schedule cache mandatory. They describe the observable
  outcome (a repeat read does not reach the database, a write is visible at once),
  not a storage technology.
- The role matrix is not repeated here. FR-011 to FR-013 reference the roles and
  the permission helper delivered in 001-foundation, which remain the single
  source of truth for authorization.
- Five decisions settled before drafting, with the Kyaor: overlapping shifts for
  one employee are refused, timestamps are UTC with ISO 8601 output, a shift stays
  inside one calendar day and lasts at most 12 hours, and the schedule read uses
  optional from and to with the current week starting Monday as the default.
- Validation run 2 (2026-11-26): the spec was amended at the Kyaor's request with
  User Story 4, FR-026 to FR-028, SC-007, and the matching edge cases and
  assumptions, because FR-025 had no endpoint that could trigger it. All items still
  pass against the amended spec. Scope grew by exactly one ADMIN-only account route.
- Validation run 3 (2026-11-26): FR-027 was strengthened and SC-008 added at the
  Kyaor's request, so the last-admin guard also holds when two removals run at the same
  instant. The fix touches M0's deactivation and demotion paths, which share the same rule.
  All items still pass. Scope grew by one collection in `identity`, no new endpoint.
- Validation run 4 (2026-11-26): implemented. 162 tests pass, up from 112, and Ruff is
  clean on 80 files. Two findings changed the plan's assumptions: `count()` cannot run
  inside a transaction on this backend, and a write conflict surfaces as `DatabaseError`
  at the write, so `retry_on_conflict` needed no change. Both are recorded as R17 and R18
  in `research.md`. The quickstart was executed end to end and one of its steps was
  corrected, because the edit in 6.6 overlapped the shift stored in 6.5.
