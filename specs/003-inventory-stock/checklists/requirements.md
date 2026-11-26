# Specification Quality Checklist: M2 Inventory: Stock Movement Inside One Pool

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
- Validation run 1 (2026-11-26): all items pass.
- FR-024 to FR-028 describe the single write operation as an observable rule (the number
  and the event agree, no second path exists, a lost update is a defect) and name no
  storage technology. The transactional mechanism is a planning concern.
- FR-039 to FR-042 add one attribute to the catalog item. That is a data requirement
  stated as user-visible behavior, not a schema design.
- Invariants I2 (pool isolation) and I4 (stock is never read then saved) from the
  constitution are covered by FR-020 to FR-022 and FR-024 to FR-028, and by SC-001,
  SC-003 and SC-004. I3 (one item identity) is covered by FR-005 and FR-045.
- Decision 25 (a count is an observation with no direction) is covered by FR-016 to
  FR-019. Decision 12 (no transfers) is covered by FR-021 and by the out of scope list.
  Decision 14 (unit is a label only) is an assumption. Decisions 15 and 16 (no point of
  sale, no recipe depletion) are covered by FR-013 and by the out of scope list.
- One decision was settled with the Kyaor before drafting: the low stock level is one
  nullable number per catalog item, shared by every pool, rather than per pool or per
  request. This needs no backfill and no per-store data entry, and an item without a
  level is simply never reported as low.
- Two defaults were assumed rather than asked: the online pool is readable only by roles
  that reach every store (ADMIN and REGIONAL_MANAGER), and a movement earlier than the
  newest count is refused rather than recomputed. Both are recorded in Assumptions and
  both are cheap to reverse before planning.
- Carry into `/speckit.plan`: `Product.price` is a free text field today and must become a
  real money value. This is the only catalog change left from D10.
- Carry into `/speckit.plan`: SC-004 states a concurrency level of ten, chosen from the domain
  (a store has a handful of writing devices) and not from a round number. The test must measure
  and print the real ceiling at a higher level instead of asserting one.
- FR-013 refuses a sold movement on a branch pool as a milestone policy, not as a data
  rule. The spec requires the refusal to stay in one validation rule so a future point of
  sale can lift it with no migration and no rewrite of stored events. Decision 15 in
  `docs/MACRO.md` carries the same dated note, open decision 5 records when to revisit it,
  and FR-013 is the only requirement that has to change at that point.
- Settled with the Kyaor on 2026-11-26: the catalog model keeps the name `Product`. The
  macro document decision 6, the data shape, decision 14, the glossary, and constitution
  invariant I3 were amended to match, and `specs/001-foundation/research.md` D10 no longer
  promises a rename. The prose noun stays "item" in this specification, which the glossary
  now states explicitly, because `specs/001-foundation/spec.md` already uses both words.
- Validation run 3 (2026-11-26): SC-004 was restated again after implementation, from ten
  concurrent writers to three. Measured: three retries carry three simultaneous writers on every
  run and cannot carry ten at any retry spacing, while eight retries would carry ten and the
  Kyaor rejected that cost. The no-lost-update half of the criterion still runs at twenty
  writers. `research.md` R19 holds the measurement table. The Kyaor has the reversal in writing:
  set `STOCK_ATTEMPTS = 8` and restore the ten.
- Validation run 2 (2026-11-26): three amendments at the Kyaor's request. FR-040 now names
  ADMIN and REGIONAL_MANAGER, because the region buys the stock and FR-040 as written
  contradicted that. SC-004 was restated: ten concurrent writes must all succeed, and a higher
  level must show that the stored number and the event count equal the accepted count, so no
  update is lost. FR-028 now says a write that exhausts its retries answers with a conflict
  response rather than a server error. One assumption was added for the 409. All items still
  pass. Scope did not change: same routes, same collections.
- Carry into `/speckit.plan`: `research.md` R17 and R18 of 002 say a count inside a
  transaction fails on this backend and that a write conflict surfaces at the write.
  The single write operation in FR-024 must respect both.
