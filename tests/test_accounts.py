"""User Story 2: staff accounts, created and managed inside role limits."""

import threading

import pytest
from django.db import connections
from rest_framework.test import APIClient

from apps.identity.models import Employee, User
from apps.workforce.models import Shift

PASSWORD = "test-password-123"
ACCOUNTS = "/api/accounts/"
ME = "/api/auth/me/"

STORE_DENIED = "This record is outside your store access."
ROLE_DENIED = "Your role may not perform this action."
LAST_ADMIN_DENIED = "The last active admin cannot be deactivated or demoted."

ACCOUNT_FIELDS = {
    "id",
    "email",
    "role",
    "store_ids",
    "is_active",
    "first_name",
    "last_name",
    "date_joined",
}


def detail_url(user):
    return f"{ACCOUNTS}{user.pk}/"


def body(**overrides):
    data = {
        "email": "new@example.com",
        "password": PASSWORD,
        "role": User.Role.BARISTA,
        "store_ids": [],
    }
    data.update(overrides)
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
def regional(make_user, downtown, uptown):
    return make_user(
        role=User.Role.REGIONAL_MANAGER,
        stores=[downtown, uptown],
        email="regional@example.com",
    )


@pytest.fixture
def barista(make_user, downtown):
    return make_user(
        role=User.Role.BARISTA, stores=[downtown], email="barista@example.com"
    )


@pytest.fixture
def second_client():
    """A second signed-in client, for tests that act as two people."""
    return APIClient()


# Creation as admin


@pytest.mark.parametrize("role", User.Role.values)
def test_admin_creates_each_role(as_user, admin, role):
    as_user(admin)

    response = as_user(admin).post(ACCOUNTS, body(role=role), format="json")

    assert response.status_code == 201
    assert response.data["role"] == role
    assert set(response.data) == ACCOUNT_FIELDS
    assert "password" not in response.data
    created = User.objects.get(pk=response.data["id"])
    assert created.check_password(PASSWORD)


def test_created_account_has_a_usable_password(api_client, as_user, admin):
    as_user(admin).post(ACCOUNTS, body(email="fresh@example.com"), format="json")

    response = api_client.post(
        "/api/auth/login/", {"email": "fresh@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200


def test_created_email_is_normalized(as_user, admin):
    response = as_user(admin).post(
        ACCOUNTS, body(email="  New@Example.COM "), format="json"
    )

    assert response.status_code == 201
    assert response.data["email"] == "new@example.com"


def test_duplicate_email_is_a_400(as_user, admin, barista):
    response = as_user(admin).post(
        ACCOUNTS, body(email=barista.email.upper()), format="json"
    )

    assert response.status_code == 400
    assert "email" in response.data


def test_unknown_store_is_a_400(as_user, admin):
    response = as_user(admin).post(
        ACCOUNTS, body(store_ids=["ffffffffffffffffffffffff"]), format="json"
    )

    assert response.status_code == 400
    assert "store_ids" in response.data


def test_unknown_role_is_a_400(as_user, admin):
    response = as_user(admin).post(ACCOUNTS, body(role="OWNER"), format="json")

    assert response.status_code == 400
    assert "role" in response.data


def test_admin_assigns_every_store_to_a_new_regional_manager(
    as_user, admin, downtown, uptown
):
    response = as_user(admin).post(
        ACCOUNTS,
        body(email="new-regional@example.com", role=User.Role.REGIONAL_MANAGER),
        format="json",
    )

    assert response.status_code == 201
    assert set(response.data["store_ids"]) == {str(downtown.pk), str(uptown.pk)}


# Creation as manager


def test_manager_creates_a_barista_in_an_own_store(as_user, manager, downtown):
    response = as_user(manager).post(
        ACCOUNTS,
        body(email="hired@example.com", store_ids=[str(downtown.pk)]),
        format="json",
    )

    assert response.status_code == 201
    assert response.data["store_ids"] == [str(downtown.pk)]


@pytest.mark.parametrize("role", [User.Role.ADMIN, User.Role.REGIONAL_MANAGER])
def test_manager_cannot_create_a_role_above_itself(as_user, manager, role):
    response = as_user(manager).post(
        ACCOUNTS, body(email="boss@example.com", role=role), format="json"
    )

    assert response.status_code == 403
    assert response.data == {"detail": ROLE_DENIED}


def test_manager_cannot_assign_a_foreign_store(as_user, manager, uptown):
    response = as_user(manager).post(
        ACCOUNTS,
        body(email="hired@example.com", store_ids=[str(uptown.pk)]),
        format="json",
    )

    assert response.status_code == 403
    assert response.data == {"detail": STORE_DENIED}


# Creation as regional manager


def test_regional_manager_creates_a_supervisor_in_any_store(as_user, regional, uptown):
    response = as_user(regional).post(
        ACCOUNTS,
        body(
            email="supervisor@example.com",
            role=User.Role.SUPERVISOR,
            store_ids=[str(uptown.pk)],
        ),
        format="json",
    )

    assert response.status_code == 201
    assert response.data["store_ids"] == [str(uptown.pk)]


@pytest.mark.parametrize("role", [User.Role.ADMIN, User.Role.REGIONAL_MANAGER])
def test_regional_manager_cannot_create_a_role_above_itself(as_user, regional, role):
    response = as_user(regional).post(
        ACCOUNTS, body(email="boss@example.com", role=role), format="json"
    )

    assert response.status_code == 403
    assert response.data == {"detail": ROLE_DENIED}


# Listing


def test_admin_list_is_paginated(as_user, admin, barista):
    response = as_user(admin).get(ACCOUNTS)

    assert response.status_code == 200
    assert set(response.data) == {"count", "next", "previous", "results"}
    assert response.data["count"] == 2


def test_manager_sees_own_store_staff_and_self(as_user, manager, downtown, make_user):
    own_barista = make_user(
        role=User.Role.BARISTA, stores=[downtown], email="a-barista@example.com"
    )
    own_supervisor = make_user(
        role=User.Role.SUPERVISOR, stores=[downtown], email="b-sup@example.com"
    )
    make_user(role=User.Role.BARISTA, email="c-elsewhere@example.com")
    make_user(role=User.Role.MANAGER, stores=[downtown], email="d-peer@example.com")

    response = as_user(manager).get(ACCOUNTS)

    assert response.status_code == 200
    emails = {row["email"] for row in response.data["results"]}
    assert emails == {manager.email, own_barista.email, own_supervisor.email}


def test_regional_manager_sees_everyone(as_user, regional, make_user):
    make_user(role=User.Role.ADMIN, email="another-admin@example.com")
    make_user(role=User.Role.BARISTA, email="someone@example.com")

    response = as_user(regional).get(ACCOUNTS)

    assert {row["email"] for row in response.data["results"]} == {
        regional.email,
        "another-admin@example.com",
        "someone@example.com",
    }


def test_list_filters_by_role(as_user, admin, barista, make_user):
    make_user(role=User.Role.SUPERVISOR, email="sup@example.com")

    response = as_user(admin).get(ACCOUNTS, {"role": User.Role.BARISTA})

    assert [row["email"] for row in response.data["results"]] == [barista.email]


def test_list_filters_by_is_active(as_user, admin, barista, make_user):
    make_user(role=User.Role.BARISTA, email="gone@example.com", is_active=False)

    response = as_user(admin).get(ACCOUNTS, {"is_active": "false"})

    assert [row["email"] for row in response.data["results"]] == ["gone@example.com"]


def test_list_filters_by_store(as_user, admin, downtown, uptown, make_user):
    make_user(role=User.Role.BARISTA, stores=[downtown], email="a@example.com")
    make_user(role=User.Role.BARISTA, stores=[uptown], email="b@example.com")
    make_user(role=User.Role.BARISTA, email="c@example.com")

    response = as_user(admin).get(ACCOUNTS, {"store": str(uptown.pk)})

    assert [row["email"] for row in response.data["results"]] == ["b@example.com"]


def test_list_is_ordered_by_email(as_user, admin, make_user):
    for email in ("c@example.com", "a@example.com", "b@example.com"):
        make_user(role=User.Role.BARISTA, email=email)

    response = as_user(admin).get(ACCOUNTS)

    emails = [row["email"] for row in response.data["results"]]
    assert emails == sorted(emails)


def test_default_page_size_is_20(as_user, admin, make_user):
    for _ in range(21):
        make_user(role=User.Role.BARISTA, password=None)

    response = as_user(admin).get(ACCOUNTS)

    assert response.data["count"] == 22
    assert len(response.data["results"]) == 20


def test_page_size_is_capped_at_100(as_user, admin, make_user):
    for _ in range(101):
        make_user(role=User.Role.BARISTA, password=None)

    response = as_user(admin).get(ACCOUNTS, {"page_size": 500})

    assert response.data["count"] == 102
    assert len(response.data["results"]) == 100


# Detail reads


def test_manager_reads_self(as_user, manager):
    response = as_user(manager).get(detail_url(manager))

    assert response.status_code == 200
    assert response.data["email"] == manager.email


def test_manager_reads_an_own_store_barista(as_user, manager, barista):
    response = as_user(manager).get(detail_url(barista))

    assert response.status_code == 200
    assert response.data["email"] == barista.email


def test_manager_cannot_read_a_cross_store_account(as_user, manager, uptown, make_user):
    stranger = make_user(role=User.Role.BARISTA, stores=[uptown])

    response = as_user(manager).get(detail_url(stranger))

    assert response.status_code == 403
    assert response.data == {"detail": STORE_DENIED}


def test_missing_account_is_404(as_user, admin):
    response = as_user(admin).get(f"{ACCOUNTS}ffffffffffffffffffffffff/")

    assert response.status_code == 404


# Updates


def test_manager_promotes_an_own_store_barista(as_user, manager, barista):
    response = as_user(manager).patch(
        detail_url(barista), {"role": User.Role.SUPERVISOR}, format="json"
    )

    assert response.status_code == 200
    assert response.data["role"] == User.Role.SUPERVISOR
    barista.refresh_from_db()
    assert barista.role == User.Role.SUPERVISOR


def test_manager_updates_own_name(as_user, manager):
    response = as_user(manager).patch(
        detail_url(manager), {"first_name": "Marta"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["first_name"] == "Marta"


@pytest.mark.parametrize("role", [User.Role.ADMIN, User.Role.REGIONAL_MANAGER])
def test_manager_cannot_promote_to_a_role_above_itself(as_user, manager, barista, role):
    response = as_user(manager).patch(
        detail_url(barista), {"role": role}, format="json"
    )

    assert response.status_code == 403
    assert response.data == {"detail": ROLE_DENIED}
    barista.refresh_from_db()
    assert barista.role == User.Role.BARISTA


def test_manager_cannot_move_a_barista_to_a_foreign_store(
    as_user, manager, barista, uptown
):
    response = as_user(manager).patch(
        detail_url(barista), {"store_ids": [str(uptown.pk)]}, format="json"
    )

    assert response.status_code == 403
    assert response.data == {"detail": STORE_DENIED}
    barista.refresh_from_db()
    assert barista.store_ids == [barista.store_ids[0]]


def test_manager_cannot_patch_a_cross_store_account(
    as_user, manager, uptown, make_user
):
    stranger = make_user(role=User.Role.BARISTA, stores=[uptown])

    response = as_user(manager).patch(
        detail_url(stranger), {"first_name": "Nope"}, format="json"
    )

    assert response.status_code == 403
    assert response.data == {"detail": STORE_DENIED}


def test_admin_resets_a_password(as_user, admin, barista, api_client):
    response = as_user(admin).patch(
        detail_url(barista), {"password": "another-password"}, format="json"
    )

    assert response.status_code == 200
    login = api_client.post(
        "/api/auth/login/", {"email": barista.email, "password": "another-password"}
    )
    assert login.status_code == 200


def test_unknown_store_on_update_is_a_400(as_user, admin, barista):
    response = as_user(admin).patch(
        detail_url(barista), {"store_ids": ["ffffffffffffffffffffffff"]}, format="json"
    )

    assert response.status_code == 400
    assert "store_ids" in response.data


# The last active admin guard


def test_last_active_admin_cannot_be_deactivated(as_user, admin):
    response = as_user(admin).patch(
        detail_url(admin), {"is_active": False}, format="json"
    )

    assert response.status_code == 403
    assert response.data == {"detail": LAST_ADMIN_DENIED}
    admin.refresh_from_db()
    assert admin.is_active is True


def test_last_active_admin_cannot_be_demoted(as_user, admin):
    response = as_user(admin).patch(
        detail_url(admin), {"role": User.Role.MANAGER}, format="json"
    )

    assert response.status_code == 403
    assert response.data == {"detail": LAST_ADMIN_DENIED}
    admin.refresh_from_db()
    assert admin.role == User.Role.ADMIN


def test_second_admin_may_be_deactivated(as_user, admin, make_user):
    peer = make_user(role=User.Role.ADMIN, email="peer@example.com")

    response = as_user(admin).patch(
        detail_url(peer), {"is_active": False}, format="json"
    )

    assert response.status_code == 200
    peer.refresh_from_db()
    assert peer.is_active is False


# Deactivation takes effect on the next request


def test_deactivated_account_is_refused_on_the_next_request(
    as_user, api_client, second_client, admin, barista
):
    as_user(barista)
    second_client.force_login(admin)

    deactivate = second_client.patch(
        detail_url(barista), {"is_active": False}, format="json"
    )

    assert deactivate.status_code == 200
    assert api_client.get(ME).status_code == 401


# Roles below manager are refused


@pytest.mark.parametrize("role", [User.Role.SUPERVISOR, User.Role.BARISTA])
def test_other_roles_cannot_reach_accounts(as_user, make_user, role):
    actor = make_user(role=role, email="actor@example.com")
    target = make_user(role=User.Role.BARISTA, email="target@example.com")
    client = as_user(actor)

    assert client.get(ACCOUNTS).status_code == 403
    assert (
        client.post(ACCOUNTS, body(email="x@example.com"), format="json").status_code
        == 403
    )
    assert client.get(detail_url(target)).status_code == 403


def test_anonymous_is_401(api_client):
    assert api_client.get(ACCOUNTS).status_code == 401


# Deleting an account (User Story 4)

SCHEDULE = "/api/shifts/"
WINDOW = {"from": "2026-11-30T00:00:00Z", "to": "2026-12-07T00:00:00Z"}


def test_admin_deletes_an_account_with_its_profile_and_shifts(
    as_user, admin, barista, downtown, make_employee, make_shift
):
    profile = make_employee(user=barista)
    shift = make_shift(employee=profile, store=downtown)

    response = as_user(admin).delete(detail_url(barista))

    assert response.status_code == 204
    assert User.objects.filter(pk=barista.pk).exists() is False
    assert Employee.objects.filter(pk=profile.pk).exists() is False
    assert Shift.objects.filter(pk=shift.pk).exists() is False
    assert as_user(admin).get(detail_url(barista)).status_code == 404


def test_an_account_without_a_profile_deletes_alone(as_user, admin, make_user):
    lone = make_user(role=User.Role.BARISTA, email="lone@example.com")

    response = as_user(admin).delete(detail_url(lone))

    assert response.status_code == 204
    assert User.objects.filter(pk=lone.pk).exists() is False


def test_only_an_admin_deletes(as_user, manager, regional, barista):
    for actor in (manager, regional, barista):
        response = as_user(actor).delete(detail_url(barista))
        assert response.status_code == 403
        assert response.data == {"detail": ROLE_DENIED}

    assert User.objects.filter(pk=barista.pk).exists() is True


def test_deleting_an_unknown_account_is_404(as_user, admin):
    response = as_user(admin).delete(f"{ACCOUNTS}ffffffffffffffffffffffff/")

    assert response.status_code == 404


def test_deleting_with_a_malformed_id_is_404(as_user, admin):
    response = as_user(admin).delete(f"{ACCOUNTS}not-an-id/")

    assert response.status_code == 404


def test_the_last_active_admin_cannot_be_deleted(as_user, admin):
    response = as_user(admin).delete(detail_url(admin))

    assert response.status_code == 403
    assert response.data == {"detail": LAST_ADMIN_DENIED}
    assert User.objects.filter(pk=admin.pk).exists() is True


def test_an_admin_may_delete_their_own_account_beside_another(
    as_user, admin, make_user
):
    make_user(role=User.Role.ADMIN, email="other-admin@example.com")

    response = as_user(admin).delete(detail_url(admin))

    assert response.status_code == 204
    assert User.objects.filter(role=User.Role.ADMIN, is_active=True).count() == 1


def test_the_schedule_stops_listing_a_deleted_person(
    as_user, admin, manager, barista, downtown, make_employee, make_shift
):
    profile = make_employee(user=barista)
    make_shift(employee=profile, store=downtown)

    before = as_user(manager).get(SCHEDULE, WINDOW)
    as_user(admin).delete(detail_url(barista))
    after = as_user(manager).get(SCHEDULE, WINDOW)

    assert before.data["count"] == 1
    assert after.data["count"] == 0


# Two removals at once (FR-027, SC-008)


def _run_together(action, first, second):
    """Run one call as each account against the other, starting at the same time."""
    barrier = threading.Barrier(2)
    statuses = []
    lock = threading.Lock()

    def call(actor, target):
        client = APIClient()
        client.force_login(actor)
        try:
            barrier.wait(timeout=10)
            response = action(client, target)
            with lock:
                statuses.append(response.status_code)
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=call, args=(first, second)),
        threading.Thread(target=call, args=(second, first)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return statuses


@pytest.mark.django_db(transaction=True)
def test_two_admins_deleting_each_other_leave_one(admin, make_user):
    peer = make_user(role=User.Role.ADMIN, email="peer@example.com")

    statuses = _run_together(
        lambda client, target: client.delete(detail_url(target)), admin, peer
    )

    assert len(statuses) == 2
    assert statuses.count(204) == 1
    assert set(statuses) <= {204, 401, 403}
    assert User.objects.filter(role=User.Role.ADMIN, is_active=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_admins_deactivating_each_other_leave_one(admin, make_user):
    peer = make_user(role=User.Role.ADMIN, email="peer@example.com")

    statuses = _run_together(
        lambda client, target: client.patch(
            detail_url(target), {"is_active": False}, format="json"
        ),
        admin,
        peer,
    )

    assert statuses.count(200) == 1
    assert set(statuses) <= {200, 401, 403}
    assert User.objects.filter(role=User.Role.ADMIN, is_active=True).count() == 1
