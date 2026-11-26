"""SC-004: concurrent writers never lose an update.

Two promises, and only one needs a number. Three writers must all succeed and the
number must equal three. At a higher level the assertion is the no-lost-update
equation instead, because three attempts per write cannot promise that every
contender on one document wins: a refused write answers 409 and changes nothing.

The measuring level stays modest on purpose. Each thread takes its own Django
connection, which is its own MongoClient, which costs two file descriptors and a
monitor thread on the database side. Forty was enough to exhaust mongod's default
soft descriptor limit and crash the container, which is why the compose file now
sets 64000.
"""

import threading
from decimal import Decimal

import pytest
from django.db import DatabaseError, connection
from rest_framework.exceptions import APIException

from apps.inventory.models import Stock, StockEvent
from apps.inventory.services import record_movement

pytestmark = pytest.mark.django_db(transaction=True)

ASSERTED_LEVEL = 3
MEASURED_LEVEL = 20


def _fire(actor, store, product, writers):
    """One delivery of one unit per writer, all released at the same instant."""
    barrier = threading.Barrier(writers)
    outcome = {"ok": 0, "refused": 0, "error": 0, "error_kinds": {}}
    guard = threading.Lock()

    def worker():
        barrier.wait()
        try:
            record_movement(
                actor,
                {
                    "product": product.pk,
                    "pool": "BRANCH",
                    "store": store.pk,
                    "type": "RECEIVED",
                    "quantity": "1",
                },
            )
            key = "ok"
        except (APIException, DatabaseError) as exc:
            key = "refused"
            with guard:
                name = type(exc).__name__
                outcome["error_kinds"][name] = outcome["error_kinds"].get(name, 0) + 1
        except Exception:  # noqa: BLE001 - counted, then asserted to be zero
            key = "error"
        finally:
            connection.close()
        with guard:
            outcome[key] += 1

    threads = [threading.Thread(target=worker) for _ in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return outcome


@pytest.fixture
def scene(make_store, make_product, make_user):
    store = make_store(name="Downtown")
    product = make_product(name="Milk", unit="L")
    manager = make_user(role="MANAGER", stores=[store])
    return manager, store, product


def test_three_writers_all_succeed(scene):
    actor, store, product = scene

    outcome = _fire(actor, store, product, ASSERTED_LEVEL)

    stock = Stock.objects.get()
    assert outcome["error"] == 0, outcome["error_kinds"]
    assert outcome["refused"] == 0, outcome["error_kinds"]
    assert outcome["ok"] == ASSERTED_LEVEL
    assert stock.current_stock == Decimal(ASSERTED_LEVEL)
    assert StockEvent.objects.count() == ASSERTED_LEVEL


def test_a_higher_level_loses_nothing(scene):
    actor, store, product = scene

    outcome = _fire(actor, store, product, MEASURED_LEVEL)

    accepted = outcome["ok"]
    stock = Stock.objects.get()
    print(
        f"\nconcurrency ceiling: {accepted} of {MEASURED_LEVEL} accepted, "
        f"{outcome['refused']} refused with a conflict"
    )
    assert outcome["error"] == 0, outcome["error_kinds"]
    assert accepted >= 1
    assert stock.current_stock == Decimal(accepted)
    assert StockEvent.objects.count() == accepted
