"""The schedule cache: a repeat read comes from the stored copy, a write is visible."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.identity.models import User
from apps.workforce.models import ScheduleSnapshot, Shift

SHIFTS = "/api/shifts/"
WINDOW = {"from": "2026-11-30T00:00:00Z", "to": "2026-12-07T00:00:00Z"}


@pytest.fixture
def downtown(make_store):
    return make_store(name="Downtown")


@pytest.fixture
def manager(make_user, downtown):
    return make_user(
        role=User.Role.MANAGER, stores=[downtown], email="manager@example.com"
    )


@pytest.fixture
def barista(make_user, downtown):
    return make_user(
        role=User.Role.BARISTA, stores=[downtown], email="barista@example.com"
    )


@pytest.fixture
def admin(make_user):
    return make_user(role=User.Role.ADMIN, email="admin@example.com")


@pytest.fixture
def profile(make_employee, barista):
    return make_employee(user=barista)


def test_a_repeat_read_is_answered_from_the_stored_copy(
    as_user, barista, manager, profile, downtown, make_shift
):
    shift = make_shift(employee=profile, store=downtown)

    first = as_user(barista).get(SHIFTS, WINDOW)
    # Bypass the service on purpose: no revision bump, so the cache must serve.
    Shift.objects.filter(pk=shift.pk).delete()
    second = as_user(barista).get(SHIFTS, WINDOW)

    assert first.data["count"] == 1
    assert second.status_code == 200
    assert second.data["count"] == 1
    assert ScheduleSnapshot.objects.count() == 1


def test_a_shift_write_is_visible_on_the_next_read(
    as_user, barista, manager, profile, downtown, make_shift
):
    as_user(barista).get(SHIFTS, WINDOW)

    response = as_user(manager).post(
        SHIFTS,
        {
            "employee_id": str(profile.pk),
            "store_id": str(downtown.pk),
            "starts_at": "2026-12-01T08:00:00Z",
            "ends_at": "2026-12-01T16:00:00Z",
        },
        format="json",
    )
    after = as_user(barista).get(SHIFTS, WINDOW)

    assert response.status_code == 201
    assert after.data["count"] == 1
    assert after.data["results"][0]["id"] == response.data["id"]


def test_a_delete_is_visible_on_the_next_read(
    as_user, barista, manager, profile, downtown, make_shift
):
    shift = make_shift(employee=profile, store=downtown)
    as_user(barista).get(SHIFTS, WINDOW)

    removed = as_user(manager).delete(f"{SHIFTS}{shift.pk}/")
    after = as_user(barista).get(SHIFTS, WINDOW)

    assert removed.status_code == 204
    assert after.data["count"] == 0


def test_snapshots_older_than_an_hour_are_dropped_on_a_miss(
    as_user, barista, manager, profile, downtown, make_shift
):
    as_user(barista).get(SHIFTS, WINDOW)
    stale = ScheduleSnapshot.objects.get()
    ScheduleSnapshot.objects.filter(pk=stale.pk).update(
        created_at=timezone.now() - timedelta(hours=2)
    )

    # A write changes the revision, so the next read misses and cleans up.
    as_user(manager).post(
        SHIFTS,
        {
            "employee_id": str(profile.pk),
            "store_id": str(downtown.pk),
            "starts_at": "2026-12-02T08:00:00Z",
            "ends_at": "2026-12-02T16:00:00Z",
        },
        format="json",
    )
    as_user(barista).get(SHIFTS, WINDOW)

    assert ScheduleSnapshot.objects.filter(pk=stale.pk).exists() is False


def test_actors_with_different_scope_do_not_share_a_page(
    as_user,
    admin,
    manager,
    profile,
    downtown,
    make_store,
    make_employee,
    make_user,
    make_shift,
):
    uptown = make_store(name="Uptown")
    other = make_user(role=User.Role.BARISTA, stores=[uptown], email="up@example.com")
    make_shift(employee=profile, store=downtown)
    make_shift(employee=make_employee(user=other), store=uptown)

    admin_view = as_user(admin).get(SHIFTS, WINDOW)
    manager_view = as_user(manager).get(SHIFTS, WINDOW)

    assert admin_view.data["count"] == 2
    assert manager_view.data["count"] == 1
    assert ScheduleSnapshot.objects.count() == 2
