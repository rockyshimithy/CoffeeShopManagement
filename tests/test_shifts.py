"""User Story 2: the rota write path, its four refusals, and the overlap guarantee."""

import threading

import pytest
from django.db import DatabaseError, connections
from django_mongodb_backend.transaction import atomic
from rest_framework.test import APIClient

from apps.identity.models import User
from apps.identity.services import _take_admin_slot
from apps.workforce.models import Shift

SHIFTS = "/api/shifts/"
ACCOUNTS = "/api/accounts/"
STORE_DENIED = "This record is outside your store access."
ROLE_DENIED = "Your role may not perform this action."


def detail_url(shift):
    return f"{SHIFTS}{shift.pk}/"


def payload(
    profile, store, starts="2026-11-30T08:00:00Z", ends="2026-11-30T16:00:00Z", **extra
):
    data = {
        "employee_id": str(profile.pk),
        "store_id": str(store.pk),
        "starts_at": starts,
        "ends_at": ends,
    }
    data.update(extra)
    return data


@pytest.fixture
def downtown(make_store):
    return make_store(name="Downtown")


@pytest.fixture
def uptown(make_store):
    return make_store(name="Uptown")


@pytest.fixture
def admin(make_user):
    return make_user(role=User.Role.ADMIN, email="admin@example.com")


@pytest.fixture
def manager(make_user, downtown):
    return make_user(
        role=User.Role.MANAGER, stores=[downtown], email="manager@example.com"
    )


@pytest.fixture
def supervisor(make_user, downtown):
    return make_user(
        role=User.Role.SUPERVISOR, stores=[downtown], email="supervisor@example.com"
    )


@pytest.fixture
def barista(make_user, downtown):
    return make_user(
        role=User.Role.BARISTA, stores=[downtown], email="barista@example.com"
    )


@pytest.fixture
def profile(make_employee, barista):
    return make_employee(user=barista)


@pytest.fixture
def outsider(make_employee, make_user, uptown):
    other = make_user(
        role=User.Role.BARISTA, stores=[uptown], email="outsider@example.com"
    )
    return make_employee(user=other)


# Creation


def test_a_manager_creates_a_shift(as_user, manager, profile, downtown):
    response = as_user(manager).post(SHIFTS, payload(profile, downtown), format="json")

    assert response.status_code == 201
    assert response.data["employee_id"] == str(profile.pk)
    assert response.data["store_name"] == "Downtown"
    assert Shift.objects.count() == 1


def test_a_supervisor_creates_a_shift(as_user, supervisor, profile, downtown):
    response = as_user(supervisor).post(
        SHIFTS, payload(profile, downtown), format="json"
    )

    assert response.status_code == 201


def test_two_overlapping_shifts_are_refused(as_user, manager, profile, downtown):
    first = as_user(manager).post(SHIFTS, payload(profile, downtown), format="json")
    second = as_user(manager).post(
        SHIFTS,
        payload(profile, downtown, "2026-11-30T15:00:00Z", "2026-11-30T20:00:00Z"),
        format="json",
    )

    assert first.status_code == 201
    assert second.status_code == 400
    assert Shift.objects.count() == 1


def test_touching_endpoints_are_allowed(as_user, manager, profile, downtown):
    first = as_user(manager).post(SHIFTS, payload(profile, downtown), format="json")
    second = as_user(manager).post(
        SHIFTS,
        payload(profile, downtown, "2026-11-30T16:00:00Z", "2026-11-30T20:00:00Z"),
        format="json",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert Shift.objects.count() == 2


def test_a_shift_crossing_midnight_is_refused(as_user, manager, profile, downtown):
    response = as_user(manager).post(
        SHIFTS,
        payload(profile, downtown, "2026-12-01T19:00:00Z", "2026-12-02T07:00:00Z"),
        format="json",
    )

    assert response.status_code == 400
    assert Shift.objects.count() == 0


def test_twelve_hours_is_allowed_and_one_second_more_is_not(
    as_user, manager, profile, downtown
):
    allowed = as_user(manager).post(
        SHIFTS,
        payload(profile, downtown, "2026-12-01T08:00:00Z", "2026-12-01T20:00:00Z"),
        format="json",
    )
    refused = as_user(manager).post(
        SHIFTS,
        payload(profile, downtown, "2026-12-02T08:00:00Z", "2026-12-02T20:00:01Z"),
        format="json",
    )

    assert allowed.status_code == 201
    assert refused.status_code == 400


def test_an_end_equal_to_the_start_is_refused(as_user, manager, profile, downtown):
    response = as_user(manager).post(
        SHIFTS,
        payload(profile, downtown, "2026-11-30T08:00:00Z", "2026-11-30T08:00:00Z"),
        format="json",
    )

    assert response.status_code == 400


def test_an_employee_of_another_store_is_refused(as_user, manager, outsider, downtown):
    response = as_user(manager).post(SHIFTS, payload(outsider, downtown), format="json")

    assert response.status_code == 400
    assert "store_id" in response.data
    assert Shift.objects.count() == 0


def test_an_unknown_employee_is_refused(as_user, manager, downtown):
    response = as_user(manager).post(
        SHIFTS,
        payload(type("P", (), {"pk": "ffffffffffffffffffffffff"})(), downtown),
        format="json",
    )

    assert response.status_code == 400
    assert "employee_id" in response.data


def test_an_unknown_store_is_refused(as_user, admin, profile):
    response = as_user(admin).post(
        SHIFTS,
        payload(profile, type("S", (), {"pk": "ffffffffffffffffffffffff"})()),
        format="json",
    )

    assert response.status_code == 400
    assert "store_id" in response.data


def test_a_barista_cannot_create_edit_or_delete(
    as_user, barista, manager, profile, downtown, make_shift
):
    create = as_user(barista).post(SHIFTS, payload(profile, downtown), format="json")
    shift = make_shift(employee=profile, store=downtown)
    edit = as_user(barista).patch(
        detail_url(shift), {"ends_at": "2026-11-30T17:00:00Z"}, format="json"
    )
    delete = as_user(barista).delete(detail_url(shift))

    assert create.status_code == 403
    assert create.data == {"detail": ROLE_DENIED}
    assert edit.status_code == 403
    assert delete.status_code == 403
    assert Shift.objects.count() == 1


# Editing


def test_a_manager_edits_the_end(as_user, manager, profile, downtown, make_shift):
    shift = make_shift(employee=profile, store=downtown)

    response = as_user(manager).patch(
        detail_url(shift), {"ends_at": "2026-11-30T17:30:00Z"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["ends_at"] == "2026-11-30T17:30:00Z"
    shift.refresh_from_db()
    assert shift.ends_at.isoformat() == "2026-11-30T17:30:00+00:00"


def test_an_edit_into_an_overlap_is_refused_and_changes_nothing(
    as_user, manager, profile, downtown, make_shift
):
    shift = make_shift(employee=profile, store=downtown)
    make_shift(
        employee=profile,
        store=downtown,
        starts_at="2026-11-30T18:00:00Z",
        ends_at="2026-11-30T20:00:00Z",
    )

    response = as_user(manager).patch(
        detail_url(shift), {"ends_at": "2026-11-30T19:00:00Z"}, format="json"
    )

    assert response.status_code == 400
    shift.refresh_from_db()
    assert shift.ends_at.isoformat() == "2026-11-30T16:00:00+00:00"


def test_an_edit_crossing_midnight_is_refused(
    as_user, manager, profile, downtown, make_shift
):
    shift = make_shift(employee=profile, store=downtown)

    response = as_user(manager).patch(
        detail_url(shift), {"ends_at": "2026-12-01T01:00:00Z"}, format="json"
    )

    assert response.status_code == 400


def test_changing_the_employee_or_the_store_is_refused(
    as_user, manager, profile, outsider, downtown, uptown, make_shift
):
    shift = make_shift(employee=profile, store=downtown)

    employee_change = as_user(manager).patch(
        detail_url(shift), {"employee_id": str(outsider.pk)}, format="json"
    )
    store_change = as_user(manager).patch(
        detail_url(shift), {"store_id": str(uptown.pk)}, format="json"
    )

    assert employee_change.status_code == 400
    assert "employee_id" in employee_change.data
    assert store_change.status_code == 400
    assert "store_id" in store_change.data


def test_a_cross_store_edit_is_forbidden(
    as_user, manager, outsider, uptown, make_shift
):
    hidden = make_shift(employee=outsider, store=uptown)

    response = as_user(manager).patch(
        detail_url(hidden), {"ends_at": "2026-11-30T17:00:00Z"}, format="json"
    )

    assert response.status_code == 403
    assert response.data == {"detail": STORE_DENIED}


# Deleting


def test_a_manager_deletes_a_shift(
    as_user, manager, barista, profile, downtown, make_shift
):
    shift = make_shift(employee=profile, store=downtown)

    deleted = as_user(manager).delete(detail_url(shift))
    detail = as_user(barista).get(detail_url(shift))

    assert deleted.status_code == 204
    assert detail.status_code == 404
    assert Shift.objects.count() == 0


def test_a_cross_store_delete_is_forbidden(
    as_user, manager, outsider, uptown, make_shift
):
    hidden = make_shift(employee=outsider, store=uptown)

    response = as_user(manager).delete(detail_url(hidden))

    assert response.status_code == 403
    assert Shift.objects.count() == 1


def test_a_deactivated_employee_keeps_their_shifts(
    as_user, admin, manager, barista, profile, downtown, make_shift
):
    make_shift(employee=profile, store=downtown)

    deactivated = as_user(admin).patch(
        f"{ACCOUNTS}{barista.pk}/", {"is_active": False}, format="json"
    )
    schedule = as_user(manager).get(
        SHIFTS, {"from": "2026-11-30T00:00:00Z", "to": "2026-12-07T00:00:00Z"}
    )

    assert deactivated.status_code == 200
    assert schedule.data["count"] == 1


# Concurrency (FR-009, SC-004)


@pytest.mark.django_db(transaction=True)
def test_the_admin_slot_serializes_two_writers():
    """Two transactions writing the guard row cannot both commit.

    This is the mechanism behind SC-004 and SC-008: a shared document turns a
    read-then-write race into a write conflict, which the retry replays.
    """
    holding = threading.Event()
    released = threading.Event()
    outcome = {}

    def first():
        try:
            with atomic():
                _take_admin_slot()
                holding.set()
                released.wait(timeout=10)
            outcome["first"] = "committed"
        except DatabaseError:
            outcome["first"] = "conflict"
        finally:
            connections.close_all()

    def second():
        holding.wait(timeout=10)
        try:
            with atomic():
                _take_admin_slot()
            outcome["second"] = "committed"
        except DatabaseError:
            outcome["second"] = "conflict"
        finally:
            connections.close_all()

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    threads[1].join(timeout=20)
    released.set()
    for thread in threads:
        thread.join(timeout=20)

    assert outcome.get("second") == "conflict"


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_overlapping_creates_keep_one_shift(manager, profile, downtown):
    barrier = threading.Barrier(2)
    statuses = []
    lock = threading.Lock()

    def create():
        client = APIClient()
        client.force_login(manager)
        try:
            barrier.wait(timeout=10)
            response = client.post(SHIFTS, payload(profile, downtown), format="json")
            with lock:
                statuses.append(response.status_code)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=create) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(statuses) == [201, 400]
    assert Shift.objects.filter(employee_id=profile.pk).count() == 1
