# Feature Specification: M0 Foundation: Identity, Roles, and Store Scoped Access

**Feature Branch**: `001-foundation`

**Created**: 2026-11-24

**Status**: Draft

**Input**: User description: "M0 Foundation from docs/MACRO.md: custom user, roles, store assignments, a single permission helper, the context split, and every store-scoped endpoint filtered by the actor's stores."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A staff member signs in and sees their access (Priority: P1)

A staff member signs in with their email and password. The system recognizes them, and their role and assigned stores decide what they can do next.

**Why this priority**: Every later milestone needs to know who is asking and which stores they may touch. Without this story there is no authorization at all, so nothing else can be built safely.

**Independent Test**: Create one user with the MANAGER role and one store assignment, sign in, and confirm the profile shows that role and that store. Nothing else needs to exist.

**Acceptance Scenarios**:

1. **Given** an active user with a valid password, **When** they sign in, **Then** they are signed in and their profile shows their email, role, and assigned stores.
2. **Given** an unknown email or a wrong password, **When** someone attempts to sign in, **Then** the attempt is refused and the message is identical in both cases.
3. **Given** a deactivated user, **When** they attempt to sign in, **Then** the attempt is refused.
4. **Given** a signed-in user, **When** they request their own profile, **Then** they receive only their own data.
5. **Given** a signed-in user, **When** they sign out, **Then** the session no longer authenticates them.

---

### User Story 2 - A platform admin onboards staff (Priority: P2)

A platform admin creates a staff account with an email, an initial password, a role, and zero or more store assignments. The admin can also list accounts, change a role, change store assignments, and deactivate an account.

**Why this priority**: The system needs a way to create the first users and to fix access later. Story 1 cannot be demonstrated for more than one person without it.

**Independent Test**: With one admin signed in, create a manager for one store, list accounts, change that manager to SUPERVISOR, then deactivate the account. Each step is visible on its own.

**Acceptance Scenarios**:

1. **Given** a signed-in admin, **When** they create an account with a valid email, a password, a role, and a store, **Then** the account exists and can sign in.
2. **Given** an existing account, **When** the admin changes its role and store assignments, **Then** the change applies to that user's next request.
3. **Given** an existing account, **When** the admin deactivates it, **Then** the user is refused at sign in and any existing session stops working on its next request.
4. **Given** an email that is already in use, **When** the admin creates another account with it, **Then** the creation is refused.
5. **Given** a role or store value that is not allowed, **When** the admin submits it, **Then** the creation is refused and the account is not stored.
6. **Given** a signed-in regional manager, **When** they create a BARISTA account in any store, **Then** the account exists. **When** they attempt to create an ADMIN account, **Then** the creation is refused.

---

### User Story 3 - Store scoped access is enforced everywhere (Priority: P3)

A manager assigned to one store sees and changes only that store's records. A platform admin sees every store. A regional manager also sees every store, but through store assignments rather than a filtering exemption. A barista can read but cannot change management data. A user with no store assignments sees an empty result rather than an error.

**Why this priority**: This is the M0 exit criteria named in the macro document. It is also the invariant that every later feature inherits.

**Independent Test**: Create two stores, one manager assigned to the first only, and one admin. List store-owned records as the manager and confirm no record from the second store appears. List again as the admin and confirm both stores appear. Then create a third store and confirm the regional manager sees it on their next request.

**Acceptance Scenarios**:

1. **Given** a manager assigned to store A, **When** they list store-owned records, **Then** no record from store B appears.
2. **Given** an admin, **When** they list store-owned records, **Then** records from every store appear.
3. **Given** a manager assigned to store A, **When** they request a store B record by its identifier, **Then** the request is refused as forbidden and the response states that the record is outside their access.
4. **Given** a user with no store assignments, **When** they list store-owned records, **Then** the result is empty and not an error.
5. **Given** a barista, **When** they attempt to create or change a store-owned record, **Then** the attempt is refused.
6. **Given** an admin acting on any store, **When** they list or change store-owned records, **Then** the store filter does not restrict them.
7. **Given** a regional manager, **When** they list store-owned records, **Then** records from every store appear.
8. **Given** an admin creates a new store, **When** the regional manager makes their next request, **Then** the new store is already in their assignments and its records appear, with no manual step.

---

### User Story 4 - An employee profile is attached to a staff account (Priority: P4)

A staff account may carry an employee profile with a hire date. The profile is the person's employment record, not a second login.

**Why this priority**: Later workforce features need a stable employment record per person. It is separable from access, so it comes after the access rules are correct.

**Independent Test**: Create a staff account, attach an employee profile with a hire date, and read it back as an admin and as the manager of the assigned store.

**Acceptance Scenarios**:

1. **Given** an existing staff account, **When** an admin attaches an employee profile with a hire date, **Then** the profile is readable and linked to that account.
2. **Given** a staff account with no employee profile, **When** that user signs in, **Then** access still works.
3. **Given** a manager, **When** they read an employee profile assigned to their store, **Then** they can read it. **When** the profile belongs to another store, **Then** it is not visible.

---

### Edge Cases

- A user whose only store is deleted keeps an empty assignment list and sees an empty store-owned result, not an error.
- A manager attempts to grant themselves the ADMIN role or a store they do not manage. The attempt is refused and nothing changes.
- A manager attempts to create or change an ADMIN account. The attempt is refused, and the target account is untouched.
- A manager attempts to create a BARISTA account in a store they are not assigned to. The attempt is refused.
- The last active admin is deactivated or demoted. The change is refused, so the system cannot be locked out of administration.
- Two admins change the same account at the same time. The later write wins and no partial combination of role and stores is stored.
- A signed-in user is deactivated mid-session. Their next request is refused.
- A request supplies an email with different letter casing from the stored one. It is treated as the same account.
- A store-owned record is requested without signing in. The request is refused as unauthenticated.
- A role value outside the five allowed values is submitted. It is refused.
- A regional manager account is created before any store exists. Its assignment list starts empty, and the first store created later appears in it automatically.
- A regional manager attempts to create or change another regional manager account, or an admin account. The attempt is refused.
- A regional manager renames a store. The change succeeds. When they attempt to delete one, the attempt is refused.
- Legacy employee records exist that have no staff account. They are not presented as valid accounts.

## Requirements *(mandatory)*

### Functional Requirements

**Identity and sign in**

- **FR-001**: The system MUST sign a person in with an email and a password.
- **FR-002**: The system MUST reject an unknown email and a wrong password with the same message, and MUST NOT reveal which one failed.
- **FR-003**: The system MUST keep a signed-in person signed in across requests until they sign out, they are deactivated, or the session expires from inactivity.
- **FR-004**: The system MUST treat the email as the unique account identifier, compared without regard to letter casing and ignoring surrounding whitespace.
- **FR-005**: The system MUST store passwords only as a non-reversible hash and MUST NOT return password data in any response.
- **FR-006**: The system MUST let a signed-in person read and update their own profile fields that are not access related. Access fields are changed only by an admin.
- **FR-007**: The system MUST refuse any request to a protected resource from an unknown or deactivated account, including a request carrying a still valid session.

**Roles and store assignments**

- **FR-008**: Every account MUST have exactly one role, from a fixed list of five: ADMIN, REGIONAL_MANAGER, MANAGER, SUPERVISOR, BARISTA.
- **FR-009**: Every staff account MUST have zero or more store assignments, and an account with none is valid.
- **FR-010**: The system MUST resolve every authorization decision through one shared permission helper, and no other code path may compare role values to decide whether an action is allowed.
- **FR-011**: The permission helper MUST answer two questions: whether this actor may perform this action, and whether this actor may act on this store.
- **FR-012**: The system MUST apply the following permission matrix.
- **FR-013**: The system MUST give ADMIN unrestricted access to every store, as the only role that bypasses the store filter.
- **FR-013A**: A regional manager MUST reach every store through store assignments, never through a filter exemption. When a store is created, the system MUST add it to the assignments of every regional manager account. When a regional manager account is created, the system MUST give it every store that already exists. The result MUST apply to the next request with no manual step.

| Action | ADMIN | REGIONAL_MANAGER | MANAGER | SUPERVISOR | BARISTA |
|---|---|---|---|---|---|
| Read stores | all stores | all stores | own stores | own stores | own stores |
| Create a store | yes | yes | no | no | no |
| Change a store | yes | yes | no | no | no |
| Delete a store | yes | no | no | no | no |
| Create, change, or deactivate a staff account | yes | BARISTA and SUPERVISOR, any store | BARISTA and SUPERVISOR, own stores | no | no |
| Change a role or store assignment | yes | BARISTA and SUPERVISOR, any store, cannot grant ADMIN or REGIONAL_MANAGER | own stores, cannot grant ADMIN or REGIONAL_MANAGER | no | no |
| Read employee profiles | all stores | all stores | own stores | own stores | own stores, names only |
| Create or change an employee profile | yes | all stores | own stores | no | no |
| Read staff account data (email, role, active) | all accounts | all accounts | BARISTA and SUPERVISOR in own stores, plus own account | own account only | own account only |

**Account administration**

- **FR-014**: An admin MUST be able to list, create, update, and deactivate any staff account. Self registration MUST NOT exist.
- **FR-014A**: A manager MUST be able to create and update BARISTA and SUPERVISOR accounts inside their own stores. A manager MUST NOT create or change an ADMIN or REGIONAL_MANAGER account, and MUST NOT assign a store outside their own assignments.
- **FR-014B**: A regional manager MUST be able to create and update BARISTA and SUPERVISOR accounts in any store. A regional manager MUST NOT create or change an ADMIN or REGIONAL_MANAGER account.
- **FR-015**: The system MUST refuse deactivating or demoting the last active admin.
- **FR-016**: The system MUST apply a role or store assignment change to the affected person's next request.
- **FR-017**: The system MUST refuse a duplicate email at account creation.

**Store scoped access**

- **FR-018**: Every read and every write of store-owned data MUST be filtered by the requesting actor's store assignments, except for ADMIN, which is unfiltered.
- **FR-019**: An endpoint that reads or writes store-owned data without applying the store filter MUST be treated as a defect even when its tests pass.
- **FR-020**: An actor with no store assignments MUST receive an empty result for store-owned lists, not an error.
- **FR-021**: A request for a store-owned record outside the actor's assignments MUST be refused with a forbidden response. The response MUST state that the record is outside the actor's access, and MUST NOT expose any field of the record.
- **FR-022**: Catalog items MUST remain global read data, visible to every signed-in person regardless of store assignment. Store filtering MUST NOT be applied to catalog items.
- **FR-023**: The system MUST refuse an unauthenticated request to any store-owned or account resource.

**Employee profile**

- **FR-024**: An employee profile MUST reference exactly one staff account and MUST carry a hire date.
- **FR-025**: A staff account MUST be able to exist without an employee profile.
- **FR-026**: The system MUST NOT create a second login for an employee. Employee data MUST NOT hold credentials of its own.

### Key Entities

- **Account**: A person who can sign in. Carries an email, a password hash, one role, an active flag, and zero or more store assignments.
- **Role**: One of ADMIN, REGIONAL_MANAGER, MANAGER, SUPERVISOR, BARISTA. Decides what an account may do, never which store it may see on its own.
- **Store assignment**: A link between one account and one store. Several per account are allowed. This is the only source of store scope.
- **Employee profile**: The employment record for an account: the linked account and a hire date. Never a login.
- **Store**: One physical coffee shop. It is the unit of scope for all store-owned data. A store carries no manager field.
- **Catalog item**: A product definition shared by every storefront. Global, not store owned.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new staff member reaches a signed-in state and can state their own role and stores in under 1 minute from receiving credentials.
- **SC-002**: An admin completes staff onboarding, meaning account plus role plus store assignments, in under 2 minutes.
- **SC-003**: Across a test with at least two stores, zero records from a store outside the actor's assignments appear in any store-owned list response. The count must be exactly zero, not merely small.
- **SC-004**: Every role decision in the codebase resolves through the single permission helper. A search for role value comparisons outside that helper and its tests finds zero occurrences.
- **SC-005**: A manager trying to reach another store's record receives a forbidden response 100 percent of the time, and no field of that record appears in the response.
- **SC-006**: A deactivated account loses access from its next request onward, with no wait and no manual step.
- **SC-007**: A reviewer can add a new store-owned endpoint by calling the permission helper once, with no new authorization code.
- **SC-008**: After a store is created, every regional manager sees it on their next request with no manual assignment step. This must hold 100 percent of the time, including the first store in a fresh install.

## Assumptions

- One role per account. A person needing two roles gets two accounts, which is accepted for now.
- A manager's account authority covers BARISTA and SUPERVISOR accounts only, inside the stores the manager is assigned to. Creating or changing an ADMIN or REGIONAL_MANAGER account stays with ADMIN.
- A regional manager sees every store because every store is in their assignments, not because the filter exempts them. Store creation and regional manager creation keep the two in sync, per FR-013A.
- A regional manager may create a store and rename an existing store, but may not delete one. Deleting a store stays with ADMIN.
- Shifts are M1, not this milestone. The Kyaor has decided that MANAGER and SUPERVISOR may schedule shifts inside their own stores, and REGIONAL_MANAGER may schedule them in any store. M0 stores no shift data; that rule binds the M1 specification.
- Admins, regional managers, and managers create accounts, within the limits in FR-014, FR-014A, and FR-014B. There is no self registration and no customer role in this milestone.
- Email, compared case-insensitively, is the sign in identifier. No username field exists.
- Passwords are set by an admin at creation and can be reset by an admin. Self service password reset is out of scope.
- A session expires after a period of inactivity. Eight hours is the default for this milestone.
- Store scope applies only to store-owned data. Catalog items are global read data.
- A first active admin is created by a one-time setup step, so a fresh install can always be administered.
- The database is empty of real data, so the legacy employee, product, and store records do not need preservation. They are replaced.
- The choice of data store engine and the migration from the current one are planning concerns, not user visible behavior. They are recorded in the plan, not in this specification.
- The management platform frontend is out of scope. This milestone delivers the behavior behind it.

## Out of Scope

- Customer accounts, registration, and the shopping cart.
- Shifts, schedules, and workforce rules. Those belong to M1.
- Inventory and stock events. Those belong to M2.
- Any 3D scene or storefront work.
- Email delivery, password reset by email, and two factor authentication.
- Deployment and hosting.

## Review Checklist

See `checklists/requirements.md` in this directory.
