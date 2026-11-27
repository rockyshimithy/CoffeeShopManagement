# Specification Quality Checklist: M3 Inventory Insight: Waste Report and Activity Feed

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
- Validation run 2 (2026-11-27): default 3 reversed after discussion. FR-012, FR-015 to
  FR-018, US2 scenarios 2 and 11, SC-004, SC-005, two edge cases, and the feed assumption
  were amended. Defaults 1 (waste only) and 2 (both bounds required, inclusive) are
  confirmed. The feature is still reads only.
- Both reads are reads. FR-030 and SC-007 exist so the milestone cannot quietly grow a
  second write path to stock or events. The single write operation from M2 stays the only
  one, which is invariant I4.
- FR-019 to FR-021 restate invariant I1 for events, and they name no storage mechanism. The
  scope rule is the same one the stock list already applies, including the online pool rule.
- FR-032 is a user facing time bound, not a latency claim about a stack. It exists so that a
  plan which scans every event for one store is caught by a measurement rather than by a
  feeling.
- The item name is read live while the actor name is a stored snapshot. This is the one
  deliberate asymmetry in the feature, and it is asserted in FR-011 and FR-024 so a later
  reader does not "fix" it.
- Four defaults were assumed rather than asked, and each is cheap to reverse before
  planning:
  1. The report is waste only, with no count discrepancy folded in.
  2. Both date bounds are required, with no default window.
  3. The feed is paged, 20 per page, because the Kyaor chose reach over the literal fixed
     window on 2026-11-27. Page 1 is still the newest 20, so the exit criterion holds.
  4. Pool visibility for both reads copies the stock list exactly, so online waste appears
     in no store report.
- Carry into `/speckit.plan`: the per item totals are a group by item over one indexed
  range, and the item labels for those totals need a batch lookup. Decide once whether the
  totals page and the event page share one aggregation, and keep it off the request path of
  the other list endpoints.
- Carry into `/speckit.plan`: `inventory.services.derived_discrepancy` already returns
  predicted minus counted. Nothing in M3 calls it, and the plan should say so, because the
  obvious next request will be a loss report that does.
- Carry into `/speckit.plan`: MACRO section 7 open decision 5 (when a branch pool accepts a
  sold movement) affects nothing here. A future branch sale will simply appear in the feed,
  because the feed reads kinds and types and does not enumerate them in a storage rule.
