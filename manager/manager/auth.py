import datetime

from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError


class ProfileAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        """only-allow login from profile with no expire_on or expire_on in the future"""
        super().confirm_login_allowed(user)
        profile = getattr(user, "profile", None)
        if not profile:
            raise ValidationError("Invalid Profile", code="invalid")
        if not profile.expire_on:
            return True
        if datetime.datetime.now(tz=datetime.UTC) > profile.expire_on:
            raise ValidationError(
                f"Account has expired ({profile.expire_on})",
                code="expired",
            )
