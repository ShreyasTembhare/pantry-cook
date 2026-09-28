from __future__ import annotations

from datetime import date


def is_expired(expires_on: date | str | None, *, today: date | None = None) -> bool:
    """True when the expiry date is strictly before today.

    An item that expires today is still "use today", not expired. Missing
    dates are never expired.
    """
    if expires_on is None or expires_on == "":
        return False
    if isinstance(expires_on, str):
        expires_on = date.fromisoformat(expires_on)
    return expires_on < (today or date.today())
