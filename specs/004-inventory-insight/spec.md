# Feature Specification: M3 Inventory Insight: Waste Report and Activity Feed

**Feature Branch**: `feature/m3-inventory-insight`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "M3 inventory insight: a manager picks a date range and sees every waste event across products in their store, plus the last 20 stock changes as one timeline. Both screens read StockEvent. Exit criterion is macro section 6."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A manager reviews waste over a date range (Priority: P1)

A manager opens the waste report for their store, picks a start and an end, and sees every
waste event in that window across every item: the item, the quantity, the reason, who
recorded it, and when. The same answer carries the total wasted per item, so the manager
knows which item is losing the most before reading a single row.

**Why this priority**: This is the first M3 exit criterion, and the first read in the project
that spans items. Without it, every event recorded in M2 is only reachable one record at a
time.

**Independent Test**: Record waste against three items in one store on two different days,
then read the report for day one, for day two, and for both days, and confirm the exact
events and per item totals in all three answers.

**Acceptance Scenarios**:

1. **Given** waste of 2 on item A on day one, **When** the report for day one is read,
   **Then** one row names item A with 2, its note, its actor, and its instant.
2. **Given** waste on item A and item B in the range, **When** the report is read, **Then**
   both events appear, and the per item totals hold exactly one row per item.
3. **Given** an item wasted twice in the range, **When** the report is read, **Then** both
   events appear and that item's total is the sum of the two.
4. **Given** an event exactly at the start instant, **When** the report is read, **Then** it
   appears, because both ends of the window are included.
5. **Given** an event exactly at the end instant, **When** the report is read, **Then** it
   appears.
6. **Given** events one second before the start and one second after the end, **When** the
   report is read, **Then** neither appears.
7. **Given** a range with no waste, **When** the report is read, **Then** it answers an empty
   list and a zero total, not an error and not a not found.
8. **Given** a delivery, a sale, and a count inside the range, **When** the report is read,
   **Then** none of the three appears, because the report is waste only.
9. **Given** an item renamed after the waste was recorded, **When** the report is read,
   **Then** the row shows the item's current name.
10. **Given** a waste event recorded by a person whose account was deleted, **When** the
    report is read, **Then** the row still renders and shows the name stored on the event.
11. **Given** 2.5 and 0.25 wasted of one item, **When** the total is read, **Then** it is
    exactly 2.75 with no rounding drift.
12. **Given** a start later than the end, or a missing start, or a missing end, **When** the
    report is requested, **Then** it is refused as invalid and no partial report is returned.
13. **Given** a manager of store A, **When** they read the report, **Then** only store A's
    waste appears, and no other store's numbers appear.
14. **Given** a regional manager who reaches three stores and names no store, **When** the
    report is read, **Then** waste from all three appears and every row names its store.
15. **Given** a manager of store A, **When** they request the report for store B, **Then** it
    is refused as outside access and no field of any row is exposed.

---

### User Story 2 - A manager reads the last 20 stock changes as one timeline (Priority: P1)

A manager opens the activity feed and sees the newest changes across every item in their
store as one list, newest first: deliveries, waste, and counts together, each with the item,
what changed, who did it, when, and the note. The newest twenty arrive first, and the manager
can page back through older changes without losing the timeline.

**Why this priority**: This is the second M3 exit criterion and the only read that mixes
movements and counts across items. It is also what makes the stores feel live rather than
archived.

**Independent Test**: Record 25 changes of mixed kinds across several items, read the feed,
and confirm the first page holds exactly the 20 newest in order, the second page holds the
other 5, and no change is repeated or lost between the two.

**Acceptance Scenarios**:

1. **Given** five changes in scope, **When** the feed is read, **Then** all five appear,
   newest first.
2. **Given** 25 changes in scope, **When** the first page is read, **Then** exactly the 20
   newest appear in order, and none of the five oldest appears.
3. **Given** deliveries, waste, and counts mixed together, **When** the feed is read, **Then**
   all three kinds appear in one list ordered by instant.
4. **Given** two changes recorded at the same instant, **When** the feed is read twice,
   **Then** both appear in the same order both times.
5. **Given** a change whose actor account was deleted, **When** the feed is read, **Then**
   the row still renders with the name stored on the event.
6. **Given** a change whose item was renamed later, **When** the feed is read, **Then** the
   row shows the item's current name.
7. **Given** a manager of store A, **When** the feed is read, **Then** only store A's changes
   appear.
8. **Given** a regional manager who reaches three stores and names no store, **When** the
   feed is read, **Then** changes from all three appear and every row names its store.
9. **Given** a named store outside the actor's stores, **When** the feed is requested,
   **Then** it is refused as outside access and no field of any row is exposed.
10. **Given** a barista of store A, **When** the feed is read, **Then** they see store A's
    changes, because the feed exposes events they can already read one record at a time.
11. **Given** 25 changes in scope, **When** the second page is read, **Then** the five oldest
    appear, none of the 20 from the first page repeats, and the two pages hold 25 distinct
    changes.
12. **Given** no changes in scope, **When** the feed is read, **Then** it answers an empty
    list, not an error.
13. **Given** an unauthenticated request, **When** either read is requested, **Then** it is
    refused.

---

### User Story 3 - A manager narrows either read to one store or one item (Priority: P3)

Both reads accept a store filter and an item filter, so a manager can answer "what did we
waste of this one item" and a regional manager can answer "what changed in this one store"
without reading the scope wide list.

**Why this priority**: Both reads are complete without it. This story adds a filter over data
that already exists, so it is the cheapest slice and the safest to defer.

**Independent Test**: With waste recorded in two stores and against two items, request each
filter combination and confirm every answer is exactly its subset.

**Acceptance Scenarios**:

1. **Given** waste on items A and B in the range, **When** the report is filtered by item A,
   **Then** only A's events appear and the per item totals hold only A.
2. **Given** an actor who reaches stores A and B, **When** the report is filtered by store A,
   **Then** only store A's events and totals appear.
3. **Given** changes on items A and B, **When** the feed is filtered by item A, **Then** only
   A's changes appear.
4. **Given** a filter naming an item with no events, **When** either read is requested,
   **Then** it answers an empty result, not an error.
5. **Given** an item identifier that is not a valid identifier, **When** either read is
   requested, **Then** it is refused as invalid.
6. **Given** both filters at once, **When** either read is requested, **Then** both apply.
7. **Given** a store filter naming a store outside the actor's assignments, **When** either
   read is requested, **Then** it is refused as outside access.

---

### Edge Cases

- Both bounds are inclusive. A window whose start equals its end answers the events recorded
  at that one instant.
- Any window length is accepted. A ten year window is a valid request, and pagination, not a
  maximum range, is what bounds the event list.
- Waste recorded in the online pool appears in no store report, because that pool belongs to
  no store. It appears only for an actor who reaches every store and only when no store is
  named, which is the same visibility rule the stock list already applies.
- An event with an empty note still renders. Only waste is required to carry one, so a
  delivery or a count row shows an empty note.
- A change at the same instant as another is ordered by a stable tiebreak, so the two reads
  that follow agree and a page boundary never drops or repeats one of a tied pair arbitrarily.
- A change that falls out of the newest 20 moves to the next page rather than disappearing.
  The feed reaches the whole history, and the per record history remains the way to read one
  item's past.
- A page is an offset, so a change recorded while a manager pages can shift one entry across a
  page boundary. The order never changes, and reloading from the first page shows the current
  window.
- An item label that cannot be resolved renders as an empty name rather than failing the
  whole page, because a page of 20 should not become unusable for one missing label.
- A quantity of zero is not a legal waste movement, as in M2, so a report never has to decide
  how to display one.

## Requirements *(mandatory)*

### Functional Requirements

**Waste report**

- **FR-001**: The system MUST provide a waste report for a date range that lists every waste
  event in that range across items, newest first.
- **FR-002**: The range MUST be given as a start instant and an end instant, and both bounds
  MUST be included in the window.
- **FR-003**: A missing start, a missing end, or a start later than the end MUST be refused
  as invalid, and no partial report may be returned.
- **FR-004**: Only waste movements MUST appear. Deliveries, sales, and counts MUST NOT appear.
- **FR-005**: Each row MUST carry the item, the quantity, the note, the actor display name,
  the pool, the store when there is one, and the instant.
- **FR-006**: The report MUST carry, for every item with waste in the range, that item's total
  wasted quantity and the number of its waste events in the range.
- **FR-007**: The per item totals MUST equal the sum of that item's listed quantities in the
  range exactly, at three decimal places.
- **FR-008**: The report MUST carry a grand total for the range that equals the sum of every
  listed quantity.
- **FR-009**: The event list MUST be paginated with the same default and maximum as every
  other list, while the per item totals MUST cover the whole range rather than the current
  page.
- **FR-010**: A range with no waste MUST answer an empty list and a zero total, not an error
  and not a not found.
- **FR-011**: The item name and unit MUST be read from the catalog at read time, and the
  actor name MUST be the snapshot stored on the event.

**Activity feed**

- **FR-012**: The system MUST provide an activity feed of stock changes across items in the
  actor's scope, newest first, 20 entries per page by default.
- **FR-013**: The feed MUST include deliveries, sales, waste, and counts in one list.
- **FR-014**: Each entry MUST carry the item, the kind, the movement type or the counted
  number, the quantity where the change has one, the actor display name, the pool, the store
  when there is one, the instant, and the note.
- **FR-015**: The feed MUST paginate with the same page parameter, page size parameter,
  default of 20, maximum of 100, and page envelope as every other list, and MUST NOT cap the
  total number of entries.
- **FR-016**: At the default page size, a scope with fewer than 20 changes MUST return all of
  them on the first page.
- **FR-017**: The feed MUST be ordered by instant descending with a stable tiebreak, MUST NOT
  return an older change ahead of a newer one, and at the default page size page 1 MUST hold
  exactly the 20 newest when at least 20 changes exist.
- **FR-018**: Two reads of the same page with no write between them MUST return identical
  entries in identical order.

**Scope and roles**

- **FR-019**: Both reads MUST be filtered by the actor's store assignments, meaning every
  branch pool of an assigned store, plus the online pool only for a role that reaches every
  store.
- **FR-020**: ADMIN MUST be the only role that bypasses the store filter.
- **FR-021**: A request naming a store outside the actor's assignments MUST be refused with
  the existing outside access refusal and MUST NOT expose any field of any row.
- **FR-022**: An unauthenticated request to either read MUST be refused.
- **FR-023**: Every role that may read one stock record's history MAY read both reports, with
  no new role decision, because both expose the same events that role can already read one
  record at a time.
- **FR-024**: Deleting an account MUST NOT remove or alter an event, so both reads keep
  rendering the stored actor name.
- **FR-025**: Deleting an item or a store MUST keep both reads consistent with the existing
  cascade, so no row ever names an item or a store that no longer exists.

**Filters**

- **FR-026**: Both reads MUST accept an optional store filter and an optional item filter,
  and MUST apply both when both are given.
- **FR-027**: A store filter MUST be subject to the scope rule in FR-021.
- **FR-028**: An item filter naming an item with no events MUST answer an empty result, not
  an error. An item filter value that is not a valid identifier MUST be refused as invalid.
- **FR-029**: Filters MUST NOT change the totals rule. The per item totals and the grand total
  MUST cover the filtered range.

**Both reads**

- **FR-030**: Neither read MUST write anything, and neither MUST create, change, or delete a
  stock record or an event.
- **FR-031**: Both reads MUST be derived from stored events alone, resolving item labels from
  the catalog, and MUST NOT recompute a current stock number.
- **FR-032**: A report over one store and a 30 day range with 10,000 stored events MUST answer
  in under one second.
- **FR-033**: Every instant MUST render as ISO 8601 with an explicit offset, and every
  quantity MUST render with at most three decimal places.

### Key Entities

- **Waste event**: One stock event whose kind is a movement and whose type is waste. Carries
  the item, the pool, the store when there is one, the quantity, the actor, the instant, and
  a note that is required by M2.
- **Activity entry**: Any stock event, whether a movement or a count. A count carries a
  counted number and no direction; a movement carries a type and a quantity.
- **Item label**: The current catalog name and unit, read when the report is built. Never
  copied onto an event.
- **Actor snapshot**: The display name stored on the event at the moment it was recorded. The
  only label not read live, because the account may no longer exist.
- **Store scope**: The actor's store assignments, which decide every row in both reads.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With at least three items and two stores seeded, the report returns every waste
  event in the range exactly once, and zero events from outside the range.
- **SC-002**: For every range in the suite, the sum of the per item totals equals the sum of
  the listed quantities and equals the grand total, with a difference of exactly zero.
- **SC-003**: With at least two stores seeded, zero rows from a store outside the actor's
  assignments appear in either read, and every direct request for one is refused.
- **SC-004**: With 25 changes recorded in scope, page 1 of the feed returns exactly the 20
  newest in reverse chronological order, page 2 returns the other five, and the two pages
  together hold 25 distinct changes.
- **SC-005**: Two identical reads of the same page with no write between them return
  identical entries in identical order on every run of the suite.
- **SC-006**: A range with no waste answers a zero total and raises zero errors.
- **SC-007**: A search of the codebase finds zero new write paths to stock or events. The
  single write operation from M2 remains the only one.
- **SC-008**: A 30 day range over 10,000 stored events in one store answers in under one
  second on the development machine.
- **SC-009**: Across the suite, zero deliveries, zero sales, and zero counts appear in the
  waste report.
- **SC-010**: Every row in either read names an actor, an instant, and an item, with zero rows
  missing any of the three.

## Assumptions

- The waste report covers waste only. Count discrepancies stay where M2 put them, on one
  record's history. The macro exit criterion asks for waste events, and folding counts in
  would change what "total wasted" means.
- Both bounds are required, with no default window. A default would either hide old waste or
  need a second parameter to widen it, and the report should never answer a window the
  manager did not ask for.
- Bounds are inclusive at both ends, and the client sends the first and last instant of the
  day it means. The server does no day arithmetic, because the project has one time zone and
  a half open window would need a documented rule per client.
- The feed is paged with the shared default of 20 and maximum of 100, because a manager must
  be able to reach past changes. Page 1 is the newest 20, so the milestone exit criterion
  still describes what a manager sees first. Pages are offsets, so a change recorded between
  two reads can shift one entry across a page boundary; the order itself never changes.
- Item names and units are read live from the catalog. An item renamed today reads under its
  current name in every report. Actor names are the stored snapshot, because the person may
  no longer exist. The split is deliberate: the actor name must survive the account, while
  the item name must not become a second copy of the catalog, which I3 forbids.
- Pool visibility follows the stock list exactly. Branch pools of assigned stores always, the
  online pool only for a role that reaches every store, and the online pool never when a
  store is named. This means online waste appears in no store report. That is consistent with
  M2 and is recorded here rather than special cased.
- Roles gain no new decision. Both reads expose events a role can already read one record at
  a time, so no new permission action is introduced.
- The per item totals are derived at read time and never stored, because a stored total is a
  second source of truth for a number the events already decide.
- The events are already indexed by store and instant and by item and instant, which is what
  makes the range and item filters cheap. The plan may add one index if a measured read needs
  it.
- A deleted account keeps its events, per M2 FR-029, so both reads render the stored name.
- The item filter uses the item identifier. Filtering by name is out of scope, because names
  are not unique and the catalog has no search yet.
- Quantities are exact decimals with at most three places, as in M2. Totals inherit that rule
  and add no rounding step.
- The report is a read for a screen, not an export. No file is produced and nothing is
  scheduled.
- Instants render in ISO 8601 with an offset in the project time zone, as in 002 and 003.

## Out of Scope

- Count discrepancy inside the report, and any loss report that mixes waste with counts.
- Trend charts, period over period comparison, forecasting, and anomaly detection.
- The money value of waste. No per event cost basis is recorded, and M2 kept cost out.
- Exports to CSV or a spreadsheet, email digests, and scheduled reports.
- Waste grouped by employee. The actor is on every row, and a per person report is not in
  this milestone.
- All time counters, dashboards, and aggregates that ignore the date range.
- Archiving, purging, or compacting old events.
- Any change to how events are recorded. This milestone reads only.
- Frontend screens. This milestone delivers the behavior behind them, as 002 and 003 did.
- Alerts or notifications when waste is recorded.
- Recipe based depletion, a point of sale, and stock transfers. Decisions 12, 15, and 16
  keep all three out.

## Review Checklist

See `checklists/requirements.md` in this directory.
