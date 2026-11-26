# Feature Specification: M2 Inventory: Stock Movement Inside One Pool

**Feature Branch**: `feature/m2-inventory`

**Created**: 2026-11-26

**Status**: Draft. Amended 2026-11-26 after implementation: SC-004 states three concurrent writers, not ten, and FR-028 gained the conflict response.

**Input**: User description: "M2 Inventory from docs/MACRO.md: `Stock` and `StockEvent`. Deliveries, waste, counts, and low stock. The online pool and each store pool move independently, and a count reconciles a shelf discrepancy. Tests prove the isolation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A manager records a delivery into their store (Priority: P1)

A manager takes a delivery of milk at the back door and records it against their store. The store's number for that item rises by exactly what arrived, and the delivery appears in that item's history with who recorded it and when.

**Why this priority**: This is the first legal write to stock, so it proves the single write operation and the whole invariant set on a real collection. Nothing else in the milestone can be built without it.

**Independent Test**: Sign in as the manager of store A, record a delivery of 12 units of an item, then read the stock of store A and confirm the number rose by 12 and exactly one delivery event exists.

**Acceptance Scenarios**:

1. **Given** an item stocked in store A at 10, **When** the manager records a delivery of 12, **Then** store A reads 22 and one delivery event exists for that stock record.
2. **Given** an item with no stock yet in store A, **When** the manager records a delivery of 12, **Then** store A reads 12 and one delivery event exists.
3. **Given** a delivery of 0, **When** it is submitted, **Then** the request is refused as invalid and nothing is stored.
4. **Given** a delivery of a negative number, **When** it is submitted, **Then** the request is refused as invalid and nothing is stored.
5. **Given** a delivery of 2.75, **When** it is recorded, **Then** the store reads exactly 2.75 with no rounding drift on a repeated read.
6. **Given** a manager of store A, **When** they record a delivery into store B, **Then** the request is refused as outside their access.
7. **Given** a barista, **When** they attempt to record a delivery in their own store, **Then** the attempt is refused because of their role.
8. **Given** a barista of store A, **When** they read stock, **Then** they see the delivery and the new number.

---

### User Story 2 - The online pool and a store pool move independently (Priority: P1)

The same item is held in two places that never touch: the online pool, which the storefront sells from, and the branch pool of each store. A delivery online does not change the shelf, and waste on the shelf does not change what a customer can buy.

**Why this priority**: Pool isolation is a constitutional invariant, and it is the M2 exit criterion stated as a test. It is also the cheapest story to verify, so it gates every later stock decision.

**Independent Test**: Record a delivery online and waste in store A for the same item, then read both pools and confirm each number moved by its own operation only.

**Acceptance Scenarios**:

1. **Given** an item with 10 online and 10 in store A, **When** 3 are received online, **Then** online reads 13 and store A still reads 10.
2. **Given** the same state, **When** 4 are recorded as waste in store A, **Then** store A reads 6 and online still reads 10.
3. **Given** any single request, **When** it is accepted, **Then** at most one stock record's number changed.
4. **Given** a request that names both a store and the online pool, **When** it is submitted, **Then** it is refused as invalid, because no transfer exists.
5. **Given** a request that names a store but claims the online pool, **When** it is submitted, **Then** it is refused as invalid.
6. **Given** a request that claims a branch pool but names no store, **When** it is submitted, **Then** it is refused as invalid.
7. **Given** an item held in three stores and online, **When** the manager of store A reads stock, **Then** they see store A, and they do not see the other two stores or the online pool.

---

### User Story 3 - A manager records waste (Priority: P2)

A manager throws away expired stock and records it with a reason. The store's number falls by that amount and the loss is attributable to waste on a later report.

**Why this priority**: Waste is the only way store stock legitimately falls before counts exist, and M3 depends on it being recorded with a note and a type rather than inferred.

**Independent Test**: Record waste of 2 with a note against an item at 10 in store A, then read the number and the history.

**Acceptance Scenarios**:

1. **Given** an item at 10 in store A, **When** the manager records 2 as waste with the note "expired on Tuesday", **Then** store A reads 8 and the history holds one waste event carrying that note and that manager.
2. **Given** an item at 10, **When** the manager records 11 as waste, **Then** the request is refused as invalid, the number stays 10, and no event is stored.
3. **Given** a waste request with no note, **When** it is submitted, **Then** it is refused as invalid.
4. **Given** a waste request whose note is only whitespace, **When** it is submitted, **Then** it is refused as invalid.
5. **Given** waste recorded in store A, **When** the waste history for that item is read, **Then** the event names the actor, the instant, the quantity, and the note.

---

### User Story 4 - A count reconciles a shelf discrepancy (Priority: P2)

A manager counts what is actually on the shelf, gets a number that differs from the system, and records the count. The system now trusts the shelf. The gap between what the movements predicted and what was counted stands as the unexplained loss, and nobody had to invent a loss type to express it.

**Why this priority**: This is the second M2 exit criterion. It is also the only operation that resets the baseline, so it is the one that decides what "current" means afterwards.

**Independent Test**: Take an item whose movements predict 8, record a count of 6, then read the number, the newest count, and the derived difference.

**Acceptance Scenarios**:

1. **Given** a stock record whose current number is 8, **When** the manager records a count of 6, **Then** the number reads 6 and one count event exists carrying 6.
2. **Given** a stock record whose current number is 8, **When** the manager records a count of 11, **Then** the number reads 11, because a count sets the number and carries no direction.
3. **Given** a count of 6 recorded, **When** a delivery of 4 follows, **Then** the number reads 10.
4. **Given** a count of 6 recorded after movements that predicted 8, **When** the discrepancy is read, **Then** it reports 2 as the difference between the newest count and what the movements predicted.
5. **Given** a count event, **When** it is read, **Then** it carries no movement type and no movement quantity.
6. **Given** a count equal to the current number, **When** it is recorded, **Then** it is accepted, stored, and the number is unchanged.
7. **Given** a count of a negative number, **When** it is submitted, **Then** it is refused as invalid.
8. **Given** a count of 0, **When** it is recorded, **Then** the number reads 0, because an empty shelf is a real observation.
9. **Given** a record whose newest count is 6, **When** a movement is submitted with an instant earlier than that count, **Then** it is refused as invalid.
10. **Given** a record whose newest count is 6, **When** a movement is submitted with an instant later than that count, **Then** it is accepted and applies on top of 6.

---

### User Story 5 - A manager sees which items are low (Priority: P3)

A manager opens the low stock view for their store and sees the items that have fallen below the level set for them, worst first, so the order before opening is short.

**Why this priority**: It is the last bullet of the M2 exit criteria and it depends on everything else being correct. It adds a comparison, not a new write path.

**Independent Test**: Set a low stock level on two items, bring one below it and one to exactly it, then read the low stock list for that store.

**Acceptance Scenarios**:

1. **Given** an item with a low stock level of 5 and store A at 3, **When** the manager reads the low stock list, **Then** that item appears.
2. **Given** an item with a level of 5 and store A at exactly 5, **When** the list is read, **Then** that item does not appear, because low is strictly below.
3. **Given** an item with no level set, **When** the list is read at any quantity, **Then** that item never appears.
4. **Given** three items below their own levels, **When** the list is read, **Then** all three appear ordered by how far below the level they are, worst first.
5. **Given** an admin sets a level, **When** any store reads its list, **Then** the same level applies in every pool.
6. **Given** a manager of store A, **When** they read the list, **Then** only store A's pools and the item levels appear, and no other store's numbers appear.
7. **Given** a barista of store A, **When** they read the low stock list, **Then** they see it.

---

### Edge Cases

- An item that is not in the catalog is refused, and no stock record is created for it.
- A store that does not exist is refused, and no stock record is created for it.
- A quantity with more than three decimal places is refused, so a caller cannot store 0.0001 of a litre and make later sums unstable.
- A quantity that is not a finite number is refused.
- Two deliveries recorded at the same instant are both kept, and both count toward the number.
- A reading of a pool never creates it. Only a recorded change creates a stock record.
- A movement that would take the number below zero is refused, and the fix is a count, not a negative delivery.
- A movement whose instant is in the future is refused.
- A movement submitted with an earlier instant than the newest count of that record is refused, because the baseline it would apply to no longer exists.
- A count recorded at the same instant as a movement is resolved by instant, then by recording order, so the newest count is unambiguous.
- Two concurrent deliveries to the same pool both succeed, and the number is the sum of both. Neither overwrites the other.
- A concurrent delivery and a count leave the record consistent: the number equals the newest count plus every movement accepted after it.
- A store deleted while it holds stock takes its stock records and their events with it, in the same operation.
- An item with no stock rows answers with an empty list, not an error.
- A stock record with a number of zero is reported, not hidden.
- A stock record whose item has no low stock level is never reported as low, even at zero.
- An event is never edited or deleted by any request. History is append only.
- A record whose newest event is a movement reports that movement's instant, and a record whose newest event is a count reports the count's instant.

## Requirements *(mandatory)*

### Functional Requirements

**Stock record**

- **FR-001**: A stock record MUST identify exactly one catalog item, one pool, and, for a branch pool, exactly one store.
- **FR-002**: The pool and the store MUST agree. A branch pool requires a store, and the online pool forbids one. Any other combination is a validation failure.
- **FR-003**: There MUST be at most one stock record per item and pool.
- **FR-004**: A stock record MUST carry its current quantity, the number observed at its newest count, and the instant of its newest event.
- **FR-005**: A stock record MUST NOT copy the item's name, price, or unit. It references the item only.

**Recording a change**

- **FR-006**: A stock change MUST be one of three movement types, received, sold, or waste, where received adds and sold and waste subtract. A change MUST also be able to be a count.
- **FR-007**: Every change MUST store exactly one event carrying the stock record, the item, the pool, the store when there is one, the kind, the movement type when it is a movement, the quantity or the counted number, the actor, the instant, and the note.
- **FR-008**: A movement quantity MUST be a finite number greater than zero with at most three decimal places. Zero, negative, and more precise values are validation failures.
- **FR-009**: A movement MUST NOT take the current quantity below zero. Reaching exactly zero is allowed.
- **FR-010**: A count number MUST be a finite number, zero or greater, with at most three decimal places.
- **FR-011**: A count MUST NOT carry a movement type or a movement quantity, and a movement MUST NOT carry a counted number.
- **FR-012**: A waste movement MUST carry a note that is not empty and not only whitespace.
- **FR-013**: While no point of sale exists, a sold movement MUST be refused for a branch pool and accepted only for the online pool. This refusal MUST live in one validation rule, and MUST NOT be expressed as a storage constraint, a per-pool list of allowed movement types, a separate collection per pool, or an index. Removing the rule later MUST require no data migration and no change to any stored event.
- **FR-014**: The instant of a change MUST default to now, MUST NOT be in the future, and MUST NOT be earlier than the newest count of the same stock record.
- **FR-015**: The actor of an event MUST be the signed-in user who recorded the change. Acting on behalf of another person is not supported.

**Applying a count**

- **FR-016**: Applying a count MUST set the current quantity to the counted number and set the newest count basis to that same number.
- **FR-017**: Applying a count MUST NOT apply a sign. A count above the current number raises it, and a count below lowers it.
- **FR-018**: The system MUST NOT store a separate movement to express the gap a count closes. No surplus or shrinkage type exists, and no quantity is signed.
- **FR-019**: The difference between the newest count and the number the accepted movements predicted MUST be derivable from stored data alone.

**Pool isolation**

- **FR-020**: A single accepted operation MUST change at most one stock record.
- **FR-021**: No transfer between pools exists. A request that names two pools, or that mixes a store with the online pool, MUST be refused as invalid.
- **FR-022**: Changing one pool MUST NOT change the current quantity of any other pool of the same item.
- **FR-023**: The online pool MUST be reachable only by a role that reaches every store, and each branch pool only by actors whose store assignments include its store.

**The single write path**

- **FR-024**: Every stock change MUST go through one operation that, inside a single transaction, updates the stock record and stores its event. Storing one without the other is a defect.
- **FR-025**: Stock MUST NOT be changed by loading it, editing the value in the code, and saving it back.
- **FR-026**: The new current quantity MUST be derived inside the transaction from the stored record, never taken from the request.
- **FR-027**: No other write path to stock or events may exist, and the administrative interface MUST NOT allow direct editing of either.
- **FR-028**: Two concurrent changes to one stock record MUST both be reflected in the stored number. A change MUST NOT be lost or silently dropped. Where the backend refuses the write, the operation MUST be retried, and a write that exhausts its retries MUST be refused with a conflict response, never with a server error. That response MUST state that nothing was applied, MUST be safe to resend, and MUST tell the client how long to wait before resending so the client can supply the next round.
- **FR-029**: An event MUST never be modified or deleted by any request.

**Reads**

- **FR-030**: Stock reads MUST be filtered by the actor's store assignments. ADMIN is the only role that bypasses the filter.
- **FR-031**: A stock read MUST return the item identifier, the item name, the pool, the store when there is one, the unit label, the current quantity, the newest count, the newest event instant, and whether the record is low.
- **FR-032**: Stock lists MUST be paginated with the same default and maximum as every other list, and ordered deterministically.
- **FR-033**: The movement history of one stock record MUST be readable newest first, paginated the same way, with the actor's display name resolved.
- **FR-034**: A request for a stock record outside the actor's stores MUST be refused as forbidden with the existing outside-access message, and MUST NOT expose any field of the record.
- **FR-035**: An unauthenticated request to any stock resource MUST be refused.

**Roles**

- **FR-036**: MANAGER and SUPERVISOR MUST be able to record movements and counts for the branch pools of their own stores.
- **FR-037**: REGIONAL_MANAGER MUST be able to record movements and counts for every store, and ADMIN anywhere.
- **FR-038**: BARISTA MUST NOT record any stock change, and MUST be able to read the pools of their own stores.

**Low stock**

- **FR-039**: Each catalog item MAY carry one low stock level, shared by every pool of that item.
- **FR-040**: ADMIN and REGIONAL_MANAGER MUST be able to set and clear an item's low stock level. No other role may change it.
- **FR-041**: A stock record MUST be reported as low when its current quantity is strictly below its item's level. Equality is not low.
- **FR-042**: An item without a level MUST never be reported as low.
- **FR-043**: The low stock list MUST be filtered by store scope exactly like every other stock read, and ordered from furthest below the level to least.

**Lifecycle**

- **FR-044**: Deleting a store MUST remove its stock records and their events in the same operation.
- **FR-045**: A stock record MUST reference an existing item and an existing store, and a request naming a missing one is a validation failure.

### Key Entities

- **Stock record**: How much of one item sits in one pool. Carries the item reference, the pool, the store when the pool is a branch, the current quantity, the newest counted number, and the instant of the newest event.
- **Stock event**: One change to one stock record. Carries the kind (a movement or a count), the movement type when it is a movement, the quantity when it is a movement, the counted number when it is a count, who recorded it, when, and a note.
- **Pool**: The unit of isolation. Either the single online pool, which has no store, or one branch pool belonging to one store.
- **Catalog item**: Existing from 001. Referenced by stock and never copied into it. Owns the low stock level added by this feature.
- **Store**: Existing from 001. The unit of scope, and the owner of its branch pool.
- **Actor**: The signed-in user who recorded an event. Never editable afterwards.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Across a test that exercises both the online pool and at least two branch pools, exactly one pool's number changes per accepted operation, and the count of operations that changed two pools is zero.
- **SC-002**: For every count recorded in the test suite, the stored number afterwards equals the counted number exactly, and the discrepancy is reproducible from the stored events without any stored gap movement.
- **SC-003**: A search of the codebase for writes to stock and events finds exactly one write operation, and zero writes anywhere else, including the administrative interface.
- **SC-004**: Three concurrent deliveries of one unit to one pool leave the stored number at exactly 3 with exactly 3 events, and every one of the three requests succeeds on every run of the suite. At a higher level of concurrency, the stored number and the event count both equal the number of requests that were accepted, so zero updates are lost. A refused write answers a conflict and changes nothing.
- **SC-005**: Across a test with at least two stores, zero stock records from a store outside the actor's assignments appear in any response, and every direct request for one is refused. The count must be exactly zero.
- **SC-006**: Every role decision for stock resolves through the single permission helper from 001. A search outside that helper and its tests finds zero role comparisons for stock actions.
- **SC-007**: No accepted operation leaves a stored quantity below zero, and the count of refused overdraws in the suite equals the count of overdraws attempted.
- **SC-008**: A manager records a delivery and sees the new number on the very next read, with no wait and no manual refresh step.
- **SC-009**: In the test suite, zero items without a level are reported as low, and every item below its level is reported.
- **SC-010**: Every stored event names an actor, an instant, and a kind, with zero events missing any of the three.

## Assumptions

- Quantities are stored exactly, not as binary floating point, so that 0.1 plus 0.2 never drifts. Three decimal places is the limit, which covers litres of milk and kilograms of coffee.
- The unit label from the catalog is displayed as given and never converted. Decision 14 stands: no conversion logic exists anywhere.
- There is one branch pool per store per item. Multiple rooms, warehouses, or coolers inside one store are not modeled.
- The online pool belongs to no store, so it is visible only to roles that reach every store, which today means ADMIN and REGIONAL_MANAGER. Managers do not see online numbers in M2.
- Sales exist only in the storefront in this milestone, so a sold movement on a branch pool is refused rather than recorded. Store numbers fall only by waste and by a count. Received is the one operation that raises a number without a count.
- That refusal is a milestone policy, not a property of the stored data. A stock event already represents a branch sale with no schema change, so the day a point of sale exists counter shrinkage stops being absorbed invisibly by counts and starts appearing as recorded sales. The meaning of a count discrepancy narrows at that moment. This is a deliberate consequence of turning it on, not a defect.
- A movement earlier than the newest count is refused rather than recomputed, because the baseline it would apply to has been replaced. Backdated corrections are made with a count.
- A stock write that loses three races in a row answers 409 and is not applied. Nothing from the refused request is stored, and the client may send it again. A conflict is a reported outcome, never a server error.
- Deleting a store takes its stock with it, matching the rule already applied to shifts in 002. This feature adds no archive and no retention policy.
- Item deletion is out of scope, so nothing removes stock because its item disappeared.
- The low stock level is a single number per item shared by every pool, chosen so that no per-store data entry is needed and no existing row needs a backfill. An item without a level is simply not tracked.
- The project time zone is UTC, as in 002, and instants are rendered in ISO 8601 with an explicit offset.
- The catalog model is named `Product`, in the code and in `docs/MACRO.md` as of 2026-11-26. The price type correction belongs to planning, not to this specification.
- The schedule cache machinery from 002 is not reused here. Whether stock reads are cached is a planning concern, and correctness must not depend on a cache.
- One event is one change. Bulk imports, spreadsheet uploads, and standing orders are not in this milestone.

## Out of Scope

- Transfers between pools, in any direction, for any reason. Decision 12 makes this permanent rather than deferred.
- Recipe based depletion, where selling a drink subtracts milk. Decision 16 keeps it out.
- A point of sale, cash drawers, and till reconciliation. Decision 15 keeps store numbers moving only through recorded movements and counts.
- Supplier records, purchase orders, delivery notes, and cost per unit.
- Restocking suggestions beyond a low stock flag, and automatic reordering.
- Batch, lot, and expiry tracking, barcode scanning, and serial numbers.
- The waste report and the activity feed. Both are M3.
- Catalog CRUD, and any change to what an item is beyond its low stock level.
- Archiving, purging, or compacting events, and any retention policy.
- Frontend screens for stock. This milestone delivers the behavior behind them.

## Review Checklist

See `checklists/requirements.md` in this directory.
