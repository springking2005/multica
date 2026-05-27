"""Authentication helpers for API clients and local daemon setup."""

from __future__ import annotations

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import PersonalAccessToken, hash_token


class PersonalAccessTokenAuthentication(BaseAuthentication):
    """Authenticate pat_/cli_ bearer tokens issued by BodiAgent."""

    keyword = "Bearer"
    supported_prefixes = ("pat_", "cli_")

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth:
            return None
        if len(auth) != 2 or auth[0].lower() != self.keyword.lower().encode():
            return None
        try:
            raw_token = auth[1].decode("utf-8")
        except UnicodeError as exc:
            raise AuthenticationFailed("Invalid bearer token.") from exc
        if not raw_token.startswith(self.supported_prefixes):
            return None

        token = (
            PersonalAccessToken.objects.filter(
                token_hash=hash_token(raw_token),
                revoked=False,
            )
            .select_related("user")
            .first()
        )
        if token is None:
            raise AuthenticationFailed("Invalid personal access token.")
        if token.expires_at is not None and token.expires_at <= timezone.now():
            raise AuthenticationFailed("Personal access token has expired.")
        if not token.user.is_active:
            raise AuthenticationFailed("User is inactive.")
        token.last_used_at = timezone.now()
        token.save(update_fields=["last_used_at"])
        return (token.user, token)

    def authenticate_header(self, request):
        return self.keyword
