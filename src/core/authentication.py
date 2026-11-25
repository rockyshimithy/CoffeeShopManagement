from rest_framework.authentication import (
    SessionAuthentication as DRFSessionAuthentication,
)


class SessionAuthentication(DRFSessionAuthentication):
    """Session auth that answers 401, not 403, when no session exists.

    DRF only sends 401 when an authenticator offers a challenge. Without a
    challenge header, an anonymous request is answered 403, which the API
    contract forbids: a missing or invalid session must return 401.
    """

    def authenticate_header(self, request):
        return "Session"
