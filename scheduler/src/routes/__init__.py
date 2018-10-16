from functools import wraps
from flask import request
from jwt import exceptions as jwt_exceptions
from bson.objectid import ObjectId, InvalidId

from utils.token import AccessToken
from . import errors


def authenticate(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            token = request.headers.get("token", None)
            user = AccessToken.decode(token).get("user", {})
            kwargs["user"] = user
            return f(*args, **kwargs)
        except jwt_exceptions.ExpiredSignatureError:
            raise errors.Unauthorized("token expired")
        except jwt_exceptions.InvalidTokenError:
            raise errors.Unauthorized("token invalid")
        except jwt_exceptions.PyJWTError:
            raise errors.Unauthorized("token invalid")

    return wrapper


def bson_object_id(keys: list):
    def decorate(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            for key in keys:
                object_id = kwargs.get(key, None)
                if not isinstance(key, str):
                    continue
                try:
                    object_id = ObjectId(object_id)
                    kwargs[key] = object_id
                except InvalidId:
                    raise errors.BadRequest(message="Invalid ObjectID")
            return f(*args, **kwargs)

        return wrapper

    return decorate


def only_for_roles(roles: list = None):
    def decorate(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if roles is not None:
                ensure_user_matches_role(kwargs.get("user"), roles)
            return f(*args, **kwargs)

        return wrapper

    return decorate


def ensure_user_matches_role(user, roles):
    roles = [roles] if not isinstance(roles, (list, tuple)) else roles
    if user.get("role") not in roles:
        raise errors.NotEnoughPrivilege()
