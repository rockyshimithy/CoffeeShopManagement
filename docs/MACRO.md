# CoffeeShopManagement: Macro Concept

Version: 0.9 | Created: 2026-11-20 | Updated: 2026-11-26 | Owner: Kyaor

This document is the project wide view. It is deliberately not a feature spec. Feature
specs live in `specs/NNN-slug/` and follow the chain required by
`.specify/memory/constitution.md` (Spec, Plan, Tasks, Code).

## 1. Purpose

A portfolio project first, with the option to grow into a system a real coffee shop chain
could operate. That ordering has a cost worth naming: a portfolio rewards visible surfaces
and a clean story, while an operable system rewards data integrity, audit trails, and
failure handling. Where the two pull apart, take the honest choice and record the
limitation in section 7 instead of hiding it.

## 2. The three surfaces

| Surface | Who uses it | What it does |
|---|---|---|
| Management platform | Managers, regional managers, supervisors, baristas, platform admin | Store operations: employees, shifts, inventory. Role gated. |
| Shop | Customers, and staff browsing | Fake ecommerce: browse, search, item page, cart, fake checkout. |
| 3D cafe | Visitors | Three.js walkable coffee shop interior. Sells the brand, acts as a navigation hub, and demonstrates the Three.js work. Reads nothing from the API. |

One backend answers all three. The site pages are rendered by that backend; the 3D scene is a
separate static folder inside this repo. A split
into separate repositories happens only when deployment forces it.

## 3. Bounded contexts

A context is one Django app under `src/apps/`. The constitution forbids direct model
imports between contexts, so each one exposes service functions and its own API routes.

| Context | Status | Owns |
|---|---|---|
| `identity` | exists | `User` and `Employee`, authentication, role matrix, permission helpers |
| `stores` | exists | `Store`: name, address, postal code |
| `workforce` | exists | `Shift`: who works where and when |
| `catalog` | exists | `Product`: name, description, price, unit, `low_stock_threshold`. `sellable` arrives in M4 |
| `inventory` | exists | `Stock` and `StockEvent`: how much of an item sits in one pool, and every change |
| `commerce` | proposed | `Order` with embedded `OrderItem`. Fake checkout, no payment provider |

`identity` owns both `User` and `Employee` because they describe the same person and are
created together. `workforce` owns only shifts, since that is a separate question about the
person.

### Data shapes

Collections, not tables. Every document carries an ObjectId `_id`.

```
Product     name, description, price (nullable), sellable, unit
Store       name, address, postal_code
Shift       employee_id, store_id, starts_at, ends_at
Order       reference, status, placed_at, total, items[]  (OrderItem embedded)
OrderItem   product_id, quantity, unit_price (snapshot)

User        email, password_hash, role, is_active, store_ids[]
Employee    user_id, hire_date

Stock       product_id, pool_type (BRANCH | ONLINE), store_id (null when ONLINE),
            current_stock, last_count, last_count_at, last_event_at
StockEvent  stock_id, product_id, pool_type, store_id,
            kind (MOVEMENT | COUNT),
            type (RECEIVED | SOLD | WASTE, null when kind is COUNT),
            quantity (null when kind is COUNT),
            counted (null when kind is MOVEMENT),
            by, at, note
```

There is no `Store.manager` field. Manager access comes from `role` plus `store_ids`, so
one source of truth decides who sees what.

`unit` is a display label only (`pcs`, `L`, `kg`). No conversion logic ever goes in.

| Product | `sellable` | Price | Stocked at a store |
|---|---|---|---|
| Coffee bag XYZ | yes | 12.50 | yes, sold at the counter and ground for drinks |
| Milk | no | none | yes, in litres |
| Pastry | yes | 3.20 | yes |

Milk is not a second model. It is an item that is never sold, which is why it carries no
price.

### How stock is read

`quantity` is always positive, and the sign comes from the type: `RECEIVED` adds, `SOLD`
and `WASTE` subtract. A `COUNT` has no sign at all, because a count is an observation
rather than a direction. Applying a count resets the baseline:

```
current_stock = last count + every movement after that count
```

The difference between the newest count and the number the movements predicted is the
unexplained loss, and it falls out of the two without inventing a `SHRINKAGE` type.

## 4. Settled decisions

| # | Decision | Date | Reason |
|---|---|---|---|
| 1 | One repository. Backend plus frontend folders, split only when deployment forces it. | 2026-11-20 | One place with business logic, one API to version. |
| 2 | The 3D scene is a static frontend. It reads nothing from the API. Its job is brand atmosphere, navigation, and showing the Three.js work. | 2026-11-20 | No integration surface means no backend work and nothing for M5 to break. |
| 3 | Custom `User` model with a `role` field, used for login and authorization. | 2026-11-20 | Every rule in every surface depends on it. Django makes this migration painful later, and there is no data to migrate now. |
| 4 | `Store` is the scoping unit. Queries filter by the actor's store assignments, which are many. | 2026-11-23 | One person can work at several stores, so a single field cannot express access. |
| 5 | Roles: `ADMIN`, `REGIONAL_MANAGER`, `MANAGER`, `SUPERVISOR`, `BARISTA`. Authorization is a role field plus one permission helper module. No Django groups. | 2026-11-24 | Store scoping forces object level checks anyway, so groups would add a second source of truth and remove no work. Matches the Ponytail principle. |
| 6 | One shared `Product` for identity, description, and price. Stock is separate and lives in pools. Pools never affect each other. | 2026-11-20, amended 2026-11-26 | A sale online changes only the online pool. The isolation becomes structural rather than a rule to remember. |
| 7 | Fake checkout creates a real `Order` document with embedded `OrderItem` records. | 2026-11-23 | An order line has no life outside its order, so embedding costs nothing. |
| 8 | Delivery order: workforce, inventory, inventory insight, shop, 3D, polish. | 2026-11-23 | Domain complexity first, presentation last, and the 3D scene cannot break the backend. |
| 9 | Spec-kit is the only spec workflow that produces files. Leanspec is allowed as a thinking format only, with no artifact output. | 2026-11-20 | The constitution names `.specify/` as the home of the approved chain. Two systems writing artifacts means two sources of truth. |
| 10 | Shopping is anonymous. The cart lives in the browser session. The `CUSTOMER` role and a real checkout are deferred. | 2026-11-20 | Fewer moving parts in M4. The `CUSTOMER` role stays out of the list. |
| 11 | Price lives on the item and is identical online and in store. | 2026-11-20 | One price per item, no price lists per channel. |
| 12 | No stock transfers between pools, ever. | 2026-11-20 | Isolation is the model, not a feature to add later. |
| 13 | `inventory` is its own context. | 2026-11-20 | Both `catalog` and `commerce` read stock, so a separate app avoids a cycle. |
| 14 | `Product.unit` is a display label only. No unit conversion logic. | 2026-11-20 | A stock list that says `2.5 L` is readable. A conversion engine is not needed. |
| 15 | No point of sale in scope. Store stock moves only through recorded movements and counts. Sales exist only in the shop and change only the online pool. | 2026-11-23, amended 2026-11-26 | Removes a whole subsystem and makes pool isolation consistent. Amended: the online only sale rule is a milestone policy, not a structural one. A branch pool may accept sold movements once a point of sale exists. |
| 16 | No recipe based depletion. Selling a drink does not subtract milk. | 2026-11-20 | Nothing in scope sells a drink, so the rule would be dead code. |
| 17 | MongoDB through `django-mongodb-backend`, with `ObjectIdAutoField` on every model. | 2026-11-23 | Documents fit stock history, and the backend keeps Django auth, admin, and the ORM. |
| 18 | `Stock` holds `current_stock` and `last_count`. `StockEvent` holds every movement and count in its own collection. | 2026-11-23, amended 2026-11-26 | M3 needs events across items, which embedded arrays cannot serve without scanning every document. Amended: `Stock` also holds `last_count_at`, because refusing a movement that predates the newest count needs that instant, and deriving it would cost an extra indexed read on the hottest write path. |
| 19 | Stock changes only through one service function, inside a transaction, never by loading a value, editing it in Python, and saving it. | 2026-11-23 | The number and the events are two writes, so that function is the only thing keeping them in agreement. |
| 20 | Related data on list endpoints loads by manual batch after pagination. Index on `(store_id, starts_at)`. The schedule is cached. An endpoint that must order by a related field may join instead, because a page cannot be re-sorted after pagination. | 2026-11-23, amended 2026-11-26 | `prefetch_related()` is unsupported on this backend, so the per row query has to be prevented by hand. A sort on a joined field cannot use an index, so it is only allowed where the window and the store assignments bound the working set. |
| 29 | The shop sells packaged goods only. No prepared drinks in M4, and no recipe based depletion. | 2026-11-27 | Decision 16 already forbids recipe depletion, and a drink sold without one would contradict the stock numbers a visitor can see. A drink can return later as a stocked product with its own online row, without changing the order model. |
| 30 | The site is server-rendered. Django templates render the pages, plain JavaScript enhances them, no SPA framework is used, and the shop screens call the same origin JSON API. Reference: philsebastian.com, a custom Shopify Liquid theme with jQuery, Swiper, and a theme cart, and no router. | 2026-11-27 | Four transactional screens do not repay a framework toolchain, the reference site is built this way, server rendering keeps content pages indexable, and same origin removes CORS and credential handling. A framework becomes reasonable only if the site grows an app-like shell. |
| 21 | Transactions use `django_mongodb_backend.transaction.atomic`, never `django.db.transaction`. | 2026-11-23 | Django's transaction API is a documented no-op here, so the idiomatic import fails silently. |
| 22 | `User` and `Employee` are two collections. A customer is a `User` with no `Employee` document. | 2026-11-23 | Keeps the door open for the `CUSTOMER` role without null employment fields. |
| 23 | A person can work at several stores. Access comes from `role` plus `store_ids`. `Store.manager` is dropped. | 2026-11-23 | Two sources of truth for "who runs this store" would disagree eventually. |
| 24 | Every role sees the full schedule of their own stores. Shift visibility is not cross store. | 2026-11-23 | Keeps the scoped access invariant absolute instead of carving an exception into it. |
| 25 | A count is a `StockEvent` with `kind = COUNT` and a `counted` number. No `SURPLUS` or `SHRINKAGE` types, and no signed quantities. | 2026-11-23 | A count is absolute and has no direction, so it does not belong in the movement array. |
| 26 | MANAGER and SUPERVISOR may schedule shifts inside their own stores. REGIONAL_MANAGER may schedule shifts in any store. | 2026-11-24 | The people who run a store's day are the right ones to fill its schedule. |
| 27 | `REGIONAL_MANAGER` sees every store through store assignments, not through a second filter exemption. Creating a store adds it to every regional manager, and creating a regional manager adds every existing store to them. | 2026-11-24 | Keeps invariant I1 absolute and keeps the permission helper at one rule. A region is data, not code. |
| 28 | A regional manager may create a store and rename an existing store, but may not delete one. Creating ADMIN and REGIONAL_MANAGER accounts stays with ADMIN. | 2026-11-24 | The region owns store setup and its own naming. Closing a store is a platform decision. |

## 5. Invariants

These four are promoted to `.specify/memory/constitution.md` as of 2026-11-23, under
`## Domain Invariants`. Change them there, not here.

1. Store scoped access: every endpoint that reads or writes store data filters by the
   actor's store assignments. `ADMIN` is the only bypass.
2. Pool isolation: one operation changes stock in at most one pool, and no transfer
   operation exists.
3. One product identity: a product exists once in the catalog, and stock references
   that document. Stock never copies the product's name or price. Order lines do copy the
   price, because an order records the past.
4. Stock is never read, edited in Python, and saved. Every change goes through the single
   write function, inside a transaction.

## 6. Milestones

Each milestone becomes one or more spec-kit features. A milestone is done when its spec
chain is approved and its exit criteria hold.

| Milestone | Goal | Exit criteria |
|---|---|---|
| M0 Foundation | Custom `User`, roles, `store_ids`, permission helper, context split, Mongo backend wired | A user logs in, receives a role, and every list endpoint filters by their stores |
| M1 Workforce | Employees and shifts with role rules | A manager creates, edits, and deletes a shift in their store. A barista reads the schedule. Cross store access is refused by a test |
| M2 Inventory | `Stock` and `StockEvent`, deliveries, waste, counts, low stock | Online and store pools move independently. A count reconciles a shelf discrepancy. Tests prove isolation |
| M3 Inventory insight | Waste report and activity feed | A manager picks a date range and sees every waste event across items in their store, plus the last 20 stock changes as one timeline |
| M4 Shop | Browse, search, item page, cart, fake checkout, plus the site shell: landing page, navigation, footer, and a locations page reading the public store list | A visitor finds an item, adds two, checks out, and the order plus the online stock change are visible |
| M5 3D cafe | Walkable static scene that sells the brand and routes visitors to the other two surfaces | A visitor walks in, triggers the shop link, and triggers the management login. Verified with a manual checklist, not tests |
| M6 Portfolio polish | Seed data, README rewritten, screenshots, demo notes | A stranger understands the project from the README in under two minutes |

M3 is the milestone that makes decision 18 necessary. Without a screen that reads events
across items, embedded arrays would have been the simpler choice.

## 7. Open decisions

| # | Question | Why it matters |
|---|---|---|
| 1 | Where does the 3D scene live? Same domain path, or a separate static host? | Affects CORS, routing, and how the navigation hub links out. |
| 2 | Resolved as decision 29: the shop sells packaged goods only. | Kept so the rows below keep their numbers, which earlier specs cite. |
| 3 | What does "portfolio ready" require beyond working code? | Live deployment, screenshots, and a written story all cost time that could go into features. |
| 4 | What deployment shape? One host, or a backend plus static frontends? The site must be reachable on the public internet with TLS before M6. | Deferred, but it decides whether M6 is a compose file or a cloud setup, and it decides where uploaded images live. |
| 5 | When does a branch pool begin accepting sold movements, and what reference does a branch sale carry? | Decision 15 keeps a sale online only for now. Until a point of sale exists, counter shrinkage is visible only as a count discrepancy. |

## 8. Glossary

- **Store**: one physical coffee shop. The `stores` model.
- **Product**: one thing that can be stocked or sold. The `catalog` model. Called an item in prose.
- **Shop**: the customer facing surface. Browse, cart, checkout. Sells from the online pool.
- **Supply**: an item that is stocked but never sold. Not a separate model, just an item with `sellable = False`.
- **Pool**: a place that holds stock. Either one store, or the single online pool.
- **Movement**: a relative stock change. `RECEIVED`, `SOLD`, or `WASTE`.
- **Count**: an absolute observation of what is on the shelf. Sets the baseline.
- **Context**: one Django app with its own models and public service functions.
- **Staff role**: `ADMIN`, `REGIONAL_MANAGER`, `MANAGER`, `SUPERVISOR`, `BARISTA`. Distinct from customer.
- **Spec chain**: the ordered artifacts Spec, Plan, Tasks required before code.

## 9. How work flows

1. A macro question lands here, in section 4 or section 7.
2. A milestone is chosen from section 6.
3. `specs/NNN-slug/spec.md` is written for a slice of that milestone.
4. Plan, then tasks, then code. Constitution governs the whole chain.
5. If a feature reveals that a decision in section 4 was wrong, change it here first, with
   a date and a reason, then write the code.
