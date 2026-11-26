"""User Story 4: an employee profile is attached to a staff account."""

import pytest

from apps.identity.models import Employee, User

EMPLOYEES = "/api/employees/"
ME = "/api/auth/me/"

STORE_DENIED = "This record is outside your store access."
ROLE_DENIED = "Your role may not perform this action."

EMPLOYEE_FIELDS = {"id", "user_id", "user_email", "user_name", "hire_date"}


def employee_url(employee):
    return f"{EMPLOYEES}{employee.pk}/"


def payload(user, hire_date="2026-11-01"):
    return {"user_id": str(user.pk), "hire_date": hire_date}


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
def regional(make_user, downtown, uptown):
    return make_user(
        role=User.Role.REGIONAL_MANAGER,
        stores=[downtown, uptown],
        email="regional@example.com",
    )


@pytest.fixture
def barista(make_user, downtown):
    return make_user(
        role=User.Role.BARISTA,
        stores=[downtown],
        email="ana@example.com",
        first_name="Ana",
        last_name="Silva",
    )


# Creation


def test_admin_creates_a_profile(as_user, admin, barista):
    response = as_user(admin).post(EMPLOYEES, payload(barista), format="json")

    assert response.status_code == 201
    assert set(response.data) == EMPLOYEE_FIELDS
    assert response.data["user_id"] == str(barista.pk)
    assert response.data["user_email"] == "ana@example.com"
    assert response.data["user_name"] == "Ana Silva"
    assert response.data["hire_date"] == "2026-11-01"
    assert "password" not in response.data
    assert Employee.objects.filter(user=barista).exists()


def test_manager_creates_a_profile_for_an_own_store_barista(as_user, manager, barista):
    response = as_user(manager).post(EMPLOYEES, payload(barista), format="json")

    assert response.status_code == 201
    assert Employee.objects.filter(user=barista).exists()


def test_manager_cannot_create_a_profile_for_a_cross_store_user(
    as_user, manager, make_user, uptown
):
    stranger = make_user(role=User.Role.BARISTA, stores=[uptown])

    response = as_user(manager).post(EMPLOYEES, payload(stranger), format="json")

    assert response.status_code == 403
    assert response.data == {"detail": STORE_DENIED}
    assert not Employee.objects.filter(user=stranger).exists()


def test_regional_manager_creates_a_profile_in_any_store(
    as_user, regional, make_user, uptown
):
    stranger = make_user(role=User.Role.SUPERVISOR, stores=[uptown])

    response = as_user(regional).post(EMPLOYEES, payload(stranger), format="json")

    assert response.status_code == 201


@pytest.mark.parametrize("role", [User.Role.SUPERVISOR, User.Role.BARISTA])
def test_roles_below_manager_cannot_create_a_profile(as_user, make_user, role):
    actor = make_user(role=role, email="actor@example.com")
    target = make_user(role=User.Role.BARISTA, email="target@example.com")

    response = as_user(actor).post(EMPLOYEES, payload(target), format="json")

    assert response.status_code == 403
    assert response.data == {"detail": ROLE_DENIED}
    assert not Employee.objects.filter(user=target).exists()


def test_a_second_profile_for_the_same_user_is_a_400(
    as_user, admin, barista, make_employee
):
    make_employee(user=barista)

    response = as_user(admin).post(EMPLOYEES, payload(barista), format="json")

    assert response.status_code == 400
    assert "user_id" in response.data


def test_unknown_user_is_a_400(as_user, admin):
    response = as_user(admin).post(
        EMPLOYEES,
        {"user_id": "ffffffffffffffffffffffff", "hire_date": "2026-11-01"},
        format="json",
    )

    assert response.status_code == 400
    assert "user_id" in response.data


def test_missing_hire_date_is_a_400(as_user, admin, barista):
    response = as_user(admin).post(
        EMPLOYEES, {"user_id": str(barista.pk)}, format="json"
    )

    assert response.status_code == 400
    assert "hire_date" in response.data


def test_bad_hire_date_is_a_400(as_user, admin, barista):
    response = as_user(admin).post(
        EMPLOYEES, payload(barista, hire_date="yesterday"), format="json"
    )

    assert response.status_code == 400
    assert "hire_date" in response.data


# Listing


def test_admin_lists_every_profile(
    as_user, admin, barista, make_user, make_employee, uptown
):
    colleague = make_user(role=User.Role.BARISTA, stores=[uptown])
    make_employee(user=barista)
    make_employee(user=colleague)

    response = as_user(admin).get(EMPLOYEES)

    assert response.status_code == 200
    assert response.data["count"] == 2


def test_manager_lists_own_store_profiles_only(
    as_user, manager, barista, make_user, make_employee, uptown
):
    stranger = make_user(role=User.Role.BARISTA, stores=[uptown])
    make_employee(user=barista)
    make_employee(user=stranger)

    response = as_user(manager).get(EMPLOYEES)

    assert [row["user_email"] for row in response.data["results"]] == [
        "ana@example.com"
    ]


def test_barista_list_keeps_the_name_and_drops_the_email(
    as_user, barista, make_user, make_employee, downtown
):
    colleague = make_user(
        role=User.Role.BARISTA,
        email="colleague@example.com",
        first_name="Bo",
        last_name="Costa",
        stores=[downtown],
    )
    make_employee(user=colleague)

    response = as_user(barista).get(EMPLOYEES)

    assert len(response.data["results"]) == 1
    row = response.data["results"][0]
    assert set(row) == EMPLOYEE_FIELDS - {"user_email"}
    assert row["user_name"] == "Bo Costa"


def test_barista_detail_drops_the_email(
    as_user, barista, make_user, make_employee, downtown
):
    colleague = make_user(
        role=User.Role.BARISTA, email="colleague@example.com", stores=[downtown]
    )
    profile = make_employee(user=colleague)

    response = as_user(barista).get(employee_url(profile))

    assert response.status_code == 200
    assert "user_email" not in response.data


def test_list_filters_by_store(
    as_user, admin, barista, make_user, make_employee, uptown
):
    stranger = make_user(role=User.Role.BARISTA, stores=[uptown])
    make_employee(user=barista)
    make_employee(user=stranger)

    response = as_user(admin).get(EMPLOYEES, {"store": str(uptown.pk)})

    assert [row["user_id"] for row in response.data["results"]] == [str(stranger.pk)]


def test_list_is_ordered_by_hire_date_descending(
    as_user, admin, make_user, make_employee
):
    for email, hire_date in (
        ("one@example.com", "2026-01-01"),
        ("two@example.com", "2026-06-01"),
        ("three@example.com", "2026-03-01"),
    ):
        person = make_user(role=User.Role.BARISTA, email=email)
        make_employee(user=person, hire_date=hire_date)

    response = as_user(admin).get(EMPLOYEES)

    assert [row["hire_date"] for row in response.data["results"]] == [
        "2026-06-01",
        "2026-03-01",
        "2026-01-01",
    ]


# Updates and reads


def test_manager_patches_the_hire_date(as_user, manager, barista, make_employee):
    profile = make_employee(user=barista, hire_date="2026-11-01")

    response = as_user(manager).patch(
        employee_url(profile), {"hire_date": "2026-12-01"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["hire_date"] == "2026-12-01"
    profile.refresh_from_db()
    assert str(profile.hire_date) == "2026-12-01"


def test_manager_cannot_patch_a_cross_store_profile(
    as_user, manager, make_user, make_employee, uptown
):
    stranger = make_user(role=User.Role.BARISTA, stores=[uptown])
    profile = make_employee(user=stranger)

    response = as_user(manager).patch(
        employee_url(profile), {"hire_date": "2026-12-01"}, format="json"
    )

    assert response.status_code == 403
    assert response.data == {"detail": STORE_DENIED}


def test_the_linked_user_cannot_be_changed(
    as_user, admin, barista, make_user, make_employee
):
    other = make_user(role=User.Role.BARISTA, email="other@example.com")
    profile = make_employee(user=barista)

    response = as_user(admin).patch(
        employee_url(profile), {"user_id": str(other.pk)}, format="json"
    )

    assert response.status_code == 400
    assert "user_id" in response.data
    profile.refresh_from_db()
    assert profile.user_id == barista.pk


def test_missing_profile_is_404(as_user, admin):
    response = as_user(admin).get(f"{EMPLOYEES}ffffffffffffffffffffffff/")

    assert response.status_code == 404


def test_an_account_without_a_profile_still_works(as_user, barista):
    assert not Employee.objects.filter(user=barista).exists()

    response = as_user(barista).get(ME)

    assert response.status_code == 200
    assert response.data["email"] == "ana@example.com"


def test_employees_require_a_session(api_client):
    assert api_client.get(EMPLOYEES).status_code == 401
