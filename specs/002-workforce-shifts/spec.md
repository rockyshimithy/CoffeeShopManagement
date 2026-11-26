# Feature Specification: M1 Workforce: Shifts Inside Store Scope

**Feature Branch**: `feature/m1-workforce`

**Created**: 2026-11-26

**Status**: Approved 2026-11-26. Amended 2026-11-26: account deletion for ADMIN added, so FR-025 has a trigger.

**Input**: User description: "M1 Workforce from docs/MACRO.md: employees and shifts with role rules. The employee profile shipped with 001-foundation, so this feature covers shifts: who works in which store and when, scheduled by the people who run the store."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A staff member reads the store schedule (Priority: P1)

A signed-in staff member opens the schedule for a week and sees every shift in the stores they are assigned to: who works, in which store, and from when to when. A barista reads the same schedule their manager reads.

**Why this priority**: Reading is the value a whole store needs daily, and it is the smallest slice that can be demonstrated. It also proves the store scope invariant on a new collection before any write path exists.

**Independent Test**: Seed three shifts for one store, sign in as a barista assigned to it, and confirm the current week shows exactly those three with the right names and times.

**Acceptance Scenarios**:

1. **Given** a barista assigned to store A with three shifts that week, **When** they read the schedule, **Then** all three appear with employee name, store name, start, and end.
2. **Given** a manager assigned only to store A, and a store B that also has shifts, **When** they read the schedule with no date range, **Then** only store A's shifts of the current week appear.
3. **Given** a user with no store assignments, **When** they read the schedule, **Then** the result is empty and not an error.
4. **Given** a shift in store B, **When** a store A barista requests it by identifier, **Then** the request is refused as forbidden, states that the record is outside their access, and exposes no field of the shift.
5. **Given** an admin, **When** they read the schedule, **Then** shifts from every store appear.
6. **Given** a requested window of 32 days, **When** the schedule is read, **Then** the request is refused as invalid.

---

### User Story 2 - A manager or supervisor fills the store rota (Priority: P2)

A manager or supervisor creates a shift for an employee who is already assigned to that store, chooses the start and end, edits those times, and deletes a shift that no longer applies. The system refuses a shift that overlaps another shift for the same person, crosses midnight, lasts more than 12 hours, or points at an employee outside the store.

**Why this priority**: This is the M1 exit criterion in the macro document. It is what turns the schedule from seed data into a working rota.

**Independent Test**: As the manager of store A, create a shift for a barista of store A, edit its end, then delete it, with a barista of store A reading each state.

**Acceptance Scenarios**:

1. **Given** a manager of store A and a barista of store A, **When** the manager creates a shift from 08:00 to 16:00, **Then** it is stored and appears in the schedule.
2. **Given** the same barista already has 08:00 to 16:00, **When** the manager creates 15:00 to 20:00, **Then** the creation is refused and nothing is stored.
3. **Given** the same barista already has 08:00 to 16:00, **When** the manager creates 16:00 to 20:00, **Then** it is stored, because touching endpoints do not overlap.
4. **Given** a shift from 19:00 to 07:00, **When** it is submitted, **Then** it is refused because it crosses midnight.
5. **Given** a shift from 07:00 to 20:00, **When** it is submitted, **Then** it is refused because it lasts more than 12 hours.
6. **Given** a stored shift ending at 16:00, **When** the manager edits the end to 01:00 the next day, **Then** the edit is refused and the stored end is unchanged.
7. **Given** a barista of store B, **When** the manager of store A creates a shift for that barista in store A, **Then** the creation is refused as invalid because the employee is not assigned to store A.
8. **Given** a shift in store B, **When** the manager of store A edits or deletes it, **Then** the request is refused as outside their access.
9. **Given** a supervisor of store A, **When** they create, edit, and delete a shift in store A, **Then** every action succeeds.
10. **Given** a barista, **When** they attempt to create, edit, or delete a shift, **Then** the attempt is refused because of their role.
11. **Given** a stored shift, **When** it is deleted, **Then** it no longer appears in the schedule and its detail answers as missing.

---

### User Story 3 - A regional manager or admin schedules across stores (Priority: P3)

A regional manager schedules in any store of the region, and an admin schedules anywhere. Both keep the same validation rules as a manager.

**Why this priority**: Decision 26 gives the region the same scheduling power inside every store. It completes the role matrix for shifts but adds no new mechanics beyond the store scope that already exists.

**Independent Test**: As a regional manager assigned to two stores, create one shift in each and confirm both appear in the schedule.

**Acceptance Scenarios**:

1. **Given** a regional manager with two stores, **When** they create a shift in each, **Then** both are stored.
2. **Given** a regional manager, **When** a new store is created, **Then** they can schedule in it on their next request with no manual assignment.
3. **Given** an admin, **When** they create, edit, or delete a shift in any store, **Then** every action succeeds.
4. **Given** a regional manager, **When** they attempt to create an ADMIN account, **Then** the refusal rules from 001 still apply. This feature adds no account rule.

---

### User Story 4 - An admin closes an account (Priority: P3)

An admin removes an account for a person who has left the company. The account, its employee profile, and every shift it was scheduled for are removed in one operation, so the rota never points at someone who no longer exists.

**Why this priority**: FR-025 states the outcome but M0 shipped no endpoint that could trigger it. This story is the trigger, and it is the only path that proves the cascade end to end.

**Independent Test**: Create an account with an employee profile and two shifts, sign in as an admin, delete the account, then confirm the account, the profile, and both shifts no longer answer.

**Acceptance Scenarios**:

1. **Given** an account with an employee profile and two shifts, **When** an admin deletes the account, **Then** the account, the profile, and both shifts are gone in one operation.
2. **Given** the account is the only active admin, **When** an admin deletes it, **Then** the request is refused and nothing is removed.
3. **Given** an account that is not the last active admin, **When** that admin deletes their own account, **Then** it is removed.
4. **Given** a manager, a regional manager, or a barista, **When** they attempt to delete any account, **Then** the attempt is refused because of their role.
5. **Given** an account with no employee profile, **When** an admin deletes it, **Then** the account is removed and nothing else is affected.

---

### Edge Cases

- A shift whose end equals its start is refused, because the end must be later.
- A shift that starts at 23:59 and ends at 00:01 is refused, because it crosses midnight.
- A shift of exactly 12 hours (08:00 to 20:00) is allowed. One second longer is refused.
- Two overlapping shifts for one employee in different stores are refused, because the conflict is per person, not per store.
- Two shifts that touch, where one ends when the next begins, are allowed.
- An employee deactivated after having shifts keeps those shifts in the schedule. Deactivation stops sign-in; it does not rewrite history.
- A store deleted while it has shifts loses those shifts in one operation.
- An account deleted while its employee profile has shifts loses the profile and its shifts in one operation.
- Two concurrent requests creating overlapping shifts for the same employee result in at most one stored shift.
- A window that starts before the first shift and ends after the last returns only what exists, never an error.
- Deleting the last active admin is refused, for the same reason deactivating it is refused in 001. Otherwise nobody can administer the system afterwards.
- Two admins removing each other at the same instant leave exactly one active admin. A concurrent request never passes the guard by having read a count that still includes the other one.
- Deleting an account with shifts removes those shifts, so the rota loses a row instead of showing a person who cannot sign in.
- Deleting an account that has no employee profile removes the account alone.
- Deleting the same account twice answers as missing on the second attempt.

## Requirements *(mandatory)*

### Functional Requirements

**Shift data**

- **FR-001**: A shift MUST reference exactly one employee profile, exactly one store, a start instant, and an end instant.
- **FR-002**: Shift instants MUST be stored unambiguously and rendered in ISO 8601 with an explicit offset.
- **FR-003**: A shift's end MUST be later than its start. An end equal to or earlier than the start is a validation failure.
- **FR-004**: A shift MUST start and end on the same calendar day in the project time zone. A shift crossing midnight is a validation failure.
- **FR-005**: A shift MUST last at most 12 hours. Exactly 12 is allowed; more is a validation failure.
- **FR-006**: An employee MUST NOT hold two shifts that overlap. Overlap means one starts before the other ends and ends after the other starts. Touching endpoints are not overlap.
- **FR-007**: The overlap rule applies per employee across every store.
- **FR-008**: A shift's employee MUST already be assigned to that shift's store. Otherwise the request is a validation failure.
- **FR-009**: The overlap check and the write MUST happen as one indivisible operation, so two concurrent requests cannot both succeed.
- **FR-010**: Editing a shift MUST change only its start and end. Changing the employee or the store is a delete followed by a create.

**Roles and scope**

- **FR-011**: ADMIN, REGIONAL_MANAGER, MANAGER, and SUPERVISOR MUST be able to create, edit, and delete shifts in the stores they may reach: ADMIN anywhere, REGIONAL_MANAGER in every store, MANAGER and SUPERVISOR only in their own stores.
- **FR-012**: BARISTA MUST NOT create, edit, or delete a shift.
- **FR-013**: Every role MUST be able to read the schedule of its own stores, and only those stores. ADMIN is unfiltered.
- **FR-014**: A request for a shift outside the actor's stores MUST be refused as forbidden with the existing outside-access message, and MUST NOT expose any field of the shift.
- **FR-015**: An unauthenticated request to any shift resource MUST be refused.

**Schedule read**

- **FR-016**: The schedule list MUST accept three optional filters: store, from, and to.
- **FR-017**: With no range given, the window MUST be the current week starting Monday 00:00 in the project time zone and ending at the following Monday 00:00.
- **FR-018**: With only one of from or to given, the other MUST default to seven days away, keeping a seven day window.
- **FR-019**: A window whose end is not after its start, or that spans more than 31 days, MUST be refused as invalid.
- **FR-020**: The schedule MUST be ordered by start ascending, then by employee name, and MUST be paginated with the same default and maximum as every other list.
- **FR-021**: Each shift in a response MUST carry its identifier, employee identifier, employee display name, store identifier, store name, start, and end.
- **FR-022**: A repeated read of an unchanged schedule MUST be answered from a stored copy, and any shift change MUST be visible on the next read.

**Deletion and lifecycle**

- **FR-023**: Deleting a shift MUST remove it, and its detail MUST answer as missing afterwards.
- **FR-024**: Deleting a store MUST remove its shifts in the same operation.
- **FR-025**: Deleting an account MUST remove its employee profile and that profile's shifts in the same operation.
- **FR-026**: ADMIN MUST be able to delete an account, and that deletion MUST be the single operation described in FR-025.
- **FR-027**: Removing the last active admin MUST be refused, whether the removal is a deletion, a deactivation, or a demotion. The refusal MUST hold under concurrent requests, so two simultaneous removals can never leave zero active admins.
- **FR-028**: Every role other than ADMIN MUST NOT delete an account.

### Key Entities

- **Shift**: One employee working in one store over one interval. Carries the employee reference, the store reference, a start, and an end.
- **Employee profile**: Existing from 001. Referenced by a shift and never modified by this feature.
- **Store**: Existing from 001. The unit of scope, referenced by a shift.
- **Account**: Existing from 001. The login and role record. Deleting it takes its employee profile and that profile's shifts with it.
- **Schedule window**: The store plus the time range a read asks for. Not stored; it defines one schedule response.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A manager can fill a full week in one store with at least 20 shifts, and a barista of that store sees all 20 on the next request.
- **SC-002**: Across a test with at least two stores, zero shifts from a store outside the actor's assignments appear in any schedule response, and every direct request for one is refused. The count must be exactly zero.
- **SC-003**: A shift that overlaps another for the same employee, crosses midnight, or lasts more than 12 hours is stored zero times in the test suite.
- **SC-004**: Two concurrent requests for overlapping shifts of the same employee result in exactly one stored shift, with no partial record.
- **SC-005**: A repeated read of an unchanged schedule is answered from a stored copy, and a shift change appears on the very next read.
- **SC-006**: Every role decision for shifts resolves through the single permission helper from 001. A search outside that helper and its tests finds zero role comparisons for shift actions.
- **SC-007**: Deleting an account that has an employee profile and shifts leaves zero accounts, zero profiles, and zero shifts under that id, and an attempt to delete the last active admin changes nothing.
- **SC-008**: Two concurrent requests that each remove a different active admin leave exactly one active admin. Zero active admins is never a reachable state.

## Assumptions

- The employee profile from 001 is the only employment record. This feature adds shifts and one account endpoint, deletion, and no new employee endpoints.
- The project time zone is UTC. There is no per-store time zone in M1, so "same day" and "current week" are evaluated in UTC. A store in another zone is a display concern for later.
- Overnight shifts are out of scope, because a shift must stay inside one day. If the rota later needs a night shift, the day rule and the overlap semantics must be revisited together.
- Breaks, unpaid pauses, and paid duration are not modeled. A shift is a single interval.
- One shift belongs to one employee and one store. Recurring shifts, templates, swaps, open shift claims, and notifications are not in this milestone.
- The conflict rule is per person across stores, not per store, because one person cannot work in two places at once.
- History is not preserved in M1: deleting a store or an account removes its shifts. If shift history matters later, it becomes an archive rather than a change to the delete rules.
- The 12 hour cap is a single shift rule. A daily or weekly cap on total hours per employee is out of scope, although it can be added later without changing stored data.
- The schedule cache required by the constitution is expected here. Its storage and invalidation are planning concerns, not user visible behavior.
- Account roles, store assignments, and regional manager propagation are unchanged from 001 and are reused, not rebuilt.

## Out of Scope

- Break and pause tracking inside a shift.
- Recurring shifts, shift templates, shift swaps, and open shift claims.
- Notifications, email, and calendar export.
- Overtime rules, and daily or weekly total hour caps.
- Per-store time zones and daylight saving presentation.
- Any frontend for the schedule. This milestone delivers the behavior behind it.
- Account deletion by anyone other than ADMIN, bulk deletion, anonymization, and any retention or audit trail for a deleted account.

## Review Checklist

See `checklists/requirements.md` in this directory.
