"""User Story 1: a staff member signs in, reads their profile, and signs out."""

import pytest

from apps.identity.models import User

PASSWORD = "test-password-123"
LOGIN = "/api/auth/login/"
LOGOUT = "/api/auth/logout/"
ME = "/api/auth/me/"


@pytest.fixture
def user(make_store):
    store = make_store(name="Downtown")
    return User.objects.create_user(
        email="ana@example.com",
        password=PASSWORD,
        role=User.Role.MANAGER,
        store_ids=[store.pk],
        first_name="Ana",
    )


def test_login_sets_a_session(api_client, user):
    response = api_client.post(
        LOGIN, {"email": "ana@example.com", "password": PASSWORD}, format="json"
    )

    assert response.status_code == 200
    assert response.data["email"] == "ana@example.com"
    assert response.data["role"] == User.Role.MANAGER
    assert response.data["store_ids"] == [str(user.store_ids[0])]
    assert "password" not in response.data
    assert "sessionid" in response.cookies
    assert str(api_client.session["_auth_user_id"]) == str(user.pk)


def test_login_is_case_insensitive_on_email(api_client, user):
    response = api_client.post(
        LOGIN, {"email": "  ANA@Example.com ", "password": PASSWORD}, format="json"
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "ana@example.com", "password": "wrong-password"},
        {"email": "nobody@example.com", "password": PASSWORD},
    ],
    ids=["wrong-password", "unknown-email"],
)
def test_bad_credentials_answer_identically(api_client, user, payload):
    response = api_client.post(LOGIN, payload, format="json")

    assert response.status_code == 401
    assert response.data == {"detail": "Invalid email or password."}


def test_deactivated_user_cannot_sign_in(api_client, make_user):
    make_user(email="gone@example.com", password=PASSWORD, is_active=False)

    response = api_client.post(
        LOGIN, {"email": "gone@example.com", "password": PASSWORD}, format="json"
    )

    assert response.status_code == 401
    assert response.data == {"detail": "Invalid email or password."}


def test_missing_field_is_a_400(api_client, user):
    response = api_client.post(LOGIN, {"email": "ana@example.com"}, format="json")

    assert response.status_code == 400
    assert "password" in response.data


def test_me_returns_the_caller(api_client, as_user, user):
    as_user(user)

    response = api_client.get(ME)

    assert response.status_code == 200
    assert response.data["email"] == "ana@example.com"
    assert response.data["role"] == User.Role.MANAGER
    assert response.data["store_ids"] == [str(user.store_ids[0])]
    assert response.data["is_active"] is True
    assert response.data["first_name"] == "Ana"
    assert "password" not in response.data
    assert set(response.data) == {
        "id",
        "email",
        "role",
        "store_ids",
        "is_active",
        "first_name",
        "last_name",
        "date_joined",
    }


def test_me_requires_a_session(api_client):
    assert api_client.get(ME).status_code == 401


@pytest.mark.parametrize("field", ["role", "store_ids", "is_active"])
def test_me_refuses_read_only_fields(api_client, as_user, user, field):
    as_user(user)
    original = getattr(user, field)
    payload = {
        "role": "ADMIN",
        "store_ids": [],
        "is_active": False,
    }[field]

    response = api_client.patch(ME, {field: payload}, format="json")

    assert response.status_code == 400
    assert field in response.data
    user.refresh_from_db()
    assert getattr(user, field) == original


def test_me_updates_the_writable_fields(api_client, as_user, user):
    as_user(user)

    response = api_client.patch(
        ME,
        {"first_name": "Ana Maria", "password": "a-brand-new-password"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["first_name"] == "Ana Maria"
    user.refresh_from_db()
    assert user.check_password("a-brand-new-password")


def test_logout_ends_the_session(api_client, as_user, user):
    as_user(user)

    assert api_client.post(LOGOUT).status_code == 204
    assert api_client.get(ME).status_code == 401
