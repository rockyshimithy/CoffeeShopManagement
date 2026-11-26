"""User Story 1, and the reach half of User Story 3: the scoped schedule read."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.identity.models import User
from apps.workforce.filters import start_of_week

SHIFTS = "/api/shifts/"
ACCOUNTS = "/api/accounts/"
EMPLOYEES = "/api/employees/"
STORE_DENIED = "This record is outside your store access."


def shift_url(shift):
    return f"{SHIFTS}{shift.pk}/"


def window(start="2026-11-30T00:00:00Z", end="2026-12-07T00:00:00Z"):
    return {"from": start, "to": end}


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
def regional(make_user, downtown, uptown):
    return make_user(
        role=User.Role.REGIONAL_MANAGER,
        stores=[downtown, uptown],
        email="regional@example.com",
    )


@pytest.fixture
def cashier(make_user, downtown):
    return make_user(
        role=User.Role.BARISTA, stores=[downtown], email="cashier@example.com"
    )


@pytest.fixture
def cashier_employee(make_employee, cashier):
    return make_employee(user=cashier)


@pytest.fixture
def uptown_employee(make_employee, make_user, uptown):
    other = make_user(
        role=User.Role.BARISTA, stores=[uptown], email="uptown@example.com"
    )
    return make_employee(user=other)


# Reading


def test_barista_reads_the_schedule_of_their_store(
    as_user, cashier, cashier_employee, uptown_employee, downtown, uptown, make_shift
):
    mine = make_shift(employee=cashier_employee, store=downtown)
    make_shift(employee=uptown_employee, store=uptown)

    response = as_user(cashier).get(SHIFTS, window())

    assert response.status_code == 200
    assert response.data["count"] == 1
    row = response.data["results"][0]
    assert row["id"] == str(mine.pk)
    assert row["store_id"] == str(downtown.pk)
    assert row["store_name"] == "Downtown"
    assert row["employee_id"] == str(cashier_employee.pk)
    assert row["employee_name"] == cashier.email
    assert row["starts_at"] == "2026-11-30T08:00:00Z"
    assert row["ends_at"] == "2026-11-30T16:00:00Z"
    assert set(row) == {
        "id",
        "employee_id",
        "employee_name",
        "store_id",
        "store_name",
        "starts_at",
        "ends_at",
    }


def test_manager_sees_only_their_store(
    as_user, manager, cashier_employee, uptown_employee, downtown, uptown, make_shift
):
    downtown_shift = make_shift(employee=cashier_employee, store=downtown)
    make_shift(employee=uptown_employee, store=uptown)

    response = as_user(manager).get(SHIFTS, window())

    assert response.status_code == 200
    assert [row["id"] for row in response.data["results"]] == [str(downtown_shift.pk)]


def test_an_actor_with_no_stores_reads_an_empty_list(as_user, make_user, make_shift):
    nobody = make_user(role=User.Role.MANAGER, stores=[], email="nobody@example.com")
    make_shift()

    response = as_user(nobody).get(SHIFTS, window())

    assert response.status_code == 200
    assert response.data["count"] == 0
    assert response.data["results"] == []


def test_a_shift_in_another_store_is_forbidden(
    as_user, cashier, uptown_employee, uptown, make_shift
):
    hidden = make_shift(employee=uptown_employee, store=uptown)

    response = as_user(cashier).get(shift_url(hidden))

    assert response.status_code == 403
    assert response.data == {"detail": STORE_DENIED}


def test_an_admin_reads_every_store(
    as_user, admin, cashier_employee, uptown_employee, downtown, uptown, make_shift
):
    make_shift(employee=cashier_employee, store=downtown)
    make_shift(employee=uptown_employee, store=uptown)

    response = as_user(admin).get(SHIFTS, window())

    assert response.status_code == 200
    assert response.data["count"] == 2


def test_the_default_window_is_the_current_week(
    as_user, cashier, cashier_employee, downtown, make_shift
):
    monday = start_of_week(timezone.now())
    inside = make_shift(
        employee=cashier_employee,
        store=downtown,
        starts_at=monday + timedelta(hours=8),
        ends_at=monday + timedelta(hours=16),
    )
    make_shift(
        employee=cashier_employee,
        store=downtown,
        starts_at=monday - timedelta(days=7) + timedelta(hours=8),
        ends_at=monday - timedelta(days=7) + timedelta(hours=16),
    )

    response = as_user(cashier).get(SHIFTS)

    assert response.status_code == 200
    assert [row["id"] for row in response.data["results"]] == [str(inside.pk)]


def test_a_window_over_31_days_is_invalid(as_user, cashier):
    response = as_user(cashier).get(
        SHIFTS, {"from": "2026-11-01T00:00:00Z", "to": "2026-12-03T00:00:00Z"}
    )

    assert response.status_code == 400
    assert "detail" in response.data


def test_a_backwards_window_is_invalid(as_user, cashier):
    response = as_user(cashier).get(
        SHIFTS, {"from": "2026-12-07T00:00:00Z", "to": "2026-11-30T00:00:00Z"}
    )

    assert response.status_code == 400
    assert "detail" in response.data


def test_one_bound_alone_keeps_a_seven_day_window(
    as_user, cashier, cashier_employee, downtown, make_shift
):
    in_window = make_shift(
        employee=cashier_employee,
        store=downtown,
        starts_at="2026-12-03T08:00:00Z",
        ends_at="2026-12-03T16:00:00Z",
    )
    make_shift(
        employee=cashier_employee,
        store=downtown,
        starts_at="2026-12-11T08:00:00Z",
        ends_at="2026-12-11T16:00:00Z",
    )

    response = as_user(cashier).get(SHIFTS, {"from": "2026-11-30T00:00:00Z"})

    assert response.status_code == 200
    assert [row["id"] for row in response.data["results"]] == [str(in_window.pk)]


def test_ordering_is_start_then_employee_name(
    as_user, manager, downtown, make_shift, make_employee, make_user
):
    zoe = make_user(
        role=User.Role.BARISTA,
        stores=[downtown],
        email="zoe@example.com",
        first_name="Zoe",
        last_name="Alves",
    )
    ana = make_user(
        role=User.Role.BARISTA,
        stores=[downtown],
        email="ana@example.com",
        first_name="Ana",
        last_name="Silva",
    )
    make_shift(employee=make_employee(user=zoe), store=downtown)
    make_shift(employee=make_employee(user=ana), store=downtown)

    response = as_user(manager).get(SHIFTS, window())

    assert response.status_code == 200
    assert [row["employee_name"] for row in response.data["results"]] == [
        "Ana Silva",
        "Zoe Alves",
    ]


def test_the_store_filter_narrows_and_checks_scope(
    as_user,
    manager,
    regional,
    cashier_employee,
    uptown_employee,
    downtown,
    uptown,
    make_shift,
):
    make_shift(employee=cashier_employee, store=downtown)
    make_shift(employee=uptown_employee, store=uptown)

    allowed = as_user(manager).get(SHIFTS, {**window(), "store": str(downtown.pk)})
    refused = as_user(manager).get(SHIFTS, {**window(), "store": str(uptown.pk)})
    regional_result = as_user(regional).get(
        SHIFTS, {**window(), "store": str(uptown.pk)}
    )

    assert allowed.status_code == 200
    assert allowed.data["count"] == 1
    assert refused.status_code == 403
    assert refused.data == {"detail": STORE_DENIED}
    assert regional_result.status_code == 200
    assert regional_result.data["count"] == 1


# Cross store reach (User Story 3)


def test_a_regional_manager_schedules_in_each_store(
    as_user, regional, cashier_employee, uptown_employee, downtown, uptown, make_shift
):
    make_shift(employee=cashier_employee, store=downtown)
    make_shift(employee=uptown_employee, store=uptown)

    response = as_user(regional).get(SHIFTS, window())

    assert response.status_code == 200
    assert response.data["count"] == 2


def test_a_new_store_is_schedulable_by_the_region_at_once(as_user, regional, admin):
    created = as_user(admin).post("/api/stores/", {"name": "Riverside"}, format="json")
    riverside_id = created.data["id"]
    person = as_user(admin).post(
        ACCOUNTS,
        {
            "email": "riverside@example.com",
            "password": "test-password-123",
            "role": User.Role.BARISTA,
            "store_ids": [riverside_id],
        },
        format="json",
    )
    profile = as_user(admin).post(
        EMPLOYEES,
        {"user_id": person.data["id"], "hire_date": "2026-11-01"},
        format="json",
    )

    response = as_user(regional).post(
        SHIFTS,
        {
            "employee_id": profile.data["id"],
            "store_id": riverside_id,
            "starts_at": "2026-11-30T08:00:00Z",
            "ends_at": "2026-11-30T16:00:00Z",
        },
        format="json",
    )

    assert created.status_code == 201
    assert response.status_code == 201
    assert response.data["store_name"] == "Riverside"


def test_a_supervisor_reads_their_store(
    as_user, supervisor, downtown, make_shift, make_employee
):
    make_shift(employee=make_employee(role=User.Role.BARISTA), store=downtown)

    response = as_user(supervisor).get(SHIFTS, window())

    assert response.status_code == 200
    assert response.data["count"] == 1
