import base64
import string
import uuid
from pathlib import Path

import humanfriendly
import magic
from django.conf import settings

ONE_GB = int(1e9)


def human_readable_size(size, *, binary=True):
    if isinstance(size, int | float):
        num_bytes = size
    else:
        try:
            num_bytes = humanfriendly.parse_size(size)
        except Exception:
            return "NaN"
    is_neg = num_bytes < 0
    if is_neg:
        num_bytes = abs(num_bytes)
    output = humanfriendly.format_size(num_bytes, binary=binary)
    if is_neg:
        return f"- {output}"  # noqa: RUF001
    return output


def is_valid_language(language):
    # should move to offspot/
    return language in dict(settings.OFFSPOT_LANGUAGES).keys()


def is_valid_admin_login(admin_login: str) -> bool:
    # should move to offspot/apps
    # validate for EduPi username (and clock)
    return len(admin_login) <= 31 and set(admin_login) <= set(  # noqa: PLR2004
        string.ascii_uppercase + string.ascii_lowercase + string.digits + "-" + "_"
    )


def is_valid_admin_pwd(admin_pwd: str) -> bool:
    # should move to offspot/apps
    # validate for EduPi password, WikiFundi (mediawiki) password and clock
    return len(admin_pwd) <= 31 and set(admin_pwd) <= set(  # noqa: PLR2004
        string.ascii_uppercase + string.ascii_lowercase + string.digits + "-" + "_"
    )


def get_uuid():
    """shortcut to get a human-friendly UUID"""
    return uuid.uuid4().urn[9:]


def get_if_str(data, default=None):
    """return data if it is a string, otherwise the default"""
    if isinstance(data, str):
        return data
    return default


def get_if_str_in(data, values, default=None):
    """return data if it is a str in a list of values otherwise the default"""
    if isinstance(data, str) and data in values:
        return data
    return default


def get_list_if_values_match(data, values, default=None):
    """return only the items from data which are part of values. If not a list []"""
    if default is None:
        default = []
    if not isinstance(data, list):
        return default
    return [item for item in data if item in values]


def get_nested_key(data, keys):
    """return value for a nested key inside a dict specified as ["first", "second"]"""
    if isinstance(keys, str):
        keys = [keys]
    if not len(keys):
        return None
    val = data
    try:
        for key in keys:
            val = val[key]
    except Exception:
        val = None
    return val


def is_expected_mime(b64data: str, expected_mimes: list[str]):
    """whether an fname, base64-encoded matches the supplied mime type (unsecure)"""
    content = base64.b64decode(b64data)
    try:
        return magic.detect_from_content(content[:2048]).mime_type in expected_mimes
    except UnicodeDecodeError:
        return False


def extract_branding(config, key, mimes):
    """verified fname config dict (fname, data) from a supplied config and key"""
    fname = Path(
        get_if_str(get_nested_key(config, ["branding", key, "fname"]), "styles.css")
    ).name
    data = get_if_str(get_nested_key(config, ["branding", key, "data"]), "-")
    if is_expected_mime(data, mimes):
        return {"fname": fname, "data": data}
    return None
