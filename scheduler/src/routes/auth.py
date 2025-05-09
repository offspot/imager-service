from datetime import datetime, timedelta
from uuid import UUID, uuid4

from flask import Blueprint, Response, jsonify, request
from utils.mongo import RefreshTokens, Users
from utils.token import AccessToken
from werkzeug.security import check_password_hash

from routes.errors import BadRequest, Unauthorized

blueprint = Blueprint("auth", __name__, url_prefix="/auth")


@blueprint.route("/authorize", methods=["POST"])
def authorize():
    """
    Authorize a user with username and password
    When success, return json object with access and refresh token
    """

    # get username and password from request header
    if request.content_type and "application/x-www-form-urlencoded" in request.content_type:
        username = request.form.get("username")
        password = request.form.get("password")
    else:
        username = request.headers.get("username")
        password = request.headers.get("password")
    if username is None or password is None:
        raise BadRequest()

    # check user exists
    user = Users().find_one({"username": username})
    if user is None:
        raise Unauthorized("Username incorrect")

    # check password is valid
    password_hash = user.pop("password_hash")
    is_valid = check_password_hash(password_hash, password)
    if not is_valid:
        raise Unauthorized("Password incorrect")

    # check that user is active
    if not user.get("active", False):
        raise Unauthorized("Account is disabled.")

    # generate token
    access_token = AccessToken.encode(user)
    refresh_token = uuid4()

    # store refresh token in database
    RefreshTokens().insert_one(
        {
            "token": refresh_token,
            "user_id": user["_id"],
            "expire_time": datetime.now() + timedelta(days=30),
        }
    )

    # send response
    response_json = {"access_token": access_token, "refresh_token": refresh_token}
    response = jsonify(response_json)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@blueprint.route("/token", methods=["POST"])
def token():
    """
    Issue a new set of access and refresh token after validating an old refresh token
    Old refresh token can only be used once and hence is removed from database
    Unused but expired refresh token is also deleted from database
    """

    # get old refresh token from request header
    old_token = request.headers.get("refresh-token")
    if old_token is None:
        raise BadRequest()

    # check token exists in database and get expire time and user id
    collection = RefreshTokens()
    old_token_document = collection.find_one(
        {"token": UUID(old_token)}, {"expire_time": 1, "user_id": 1}
    )
    if old_token_document is None:
        raise Unauthorized()

    # check token is not expired
    expire_time = old_token_document["expire_time"]
    if expire_time < datetime.now():
        raise Unauthorized("token expired")

    # check user exists
    user_id = old_token_document["user_id"]
    user = Users().find_one({"_id": user_id}, {"password_hash": 0})
    if user is None:
        raise Unauthorized()

    # generate token
    access_token = AccessToken.encode(user)
    refresh_token = uuid4()

    # store refresh token in database
    RefreshTokens().insert_one(
        {
            "token": refresh_token,
            "user_id": user["_id"],
            "expire_time": datetime.now() + timedelta(days=30),
        }
    )

    # delete old refresh token from database
    collection.delete_one({"token": UUID(old_token)})
    collection.delete_many({"expire_time": {"$lte": datetime.now()}})

    # send response
    response_json = {"access_token": access_token, "refresh_token": refresh_token}
    response = jsonify(response_json)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@blueprint.route("/validate", methods=["POST"])
def validate():
    """
    Validate an access token
    """
    payload = AccessToken.decode(request.headers.get("access-token"))
    if payload is None:
        raise Unauthorized()

    user = Users().find_one({"username": payload["user"]["username"]})
    if user is None:
        raise Unauthorized()

    return Response()
