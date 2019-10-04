import pymongo
from bson import ObjectId
from flask import Blueprint, request, jsonify, Response
from jsonschema import validate, ValidationError
from werkzeug.security import check_password_hash, generate_password_hash

from utils.mongo import Users
from . import (
    authenticate,
    bson_object_id,
    errors,
    ensure_user_matches_role,
    only_for_roles,
)


blueprint = Blueprint("user", __name__, url_prefix="/users")


@blueprint.route("/", methods=["GET", "POST"])
@authenticate
def collection(user: dict):
    """
    List or create users
    """

    if request.method == "GET":
        # check user permission
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        # unpack url parameters
        skip = request.args.get("skip", default=0, type=int)
        limit = request.args.get("limit", default=20, type=int)
        skip = 0 if skip < 0 else skip
        limit = 20 if limit <= 0 else limit

        # get users from database
        query = {}
        projection = {"password_hash": 0}
        cursor = (
            Users()
            .find(query, projection)
            .sort([("$natural", pymongo.ASCENDING)])
            .skip(skip)
            .limit(limit)
        )
        count = Users().count_documents(query)
        users = [user for user in cursor]

        return jsonify(
            {"meta": {"skip": skip, "limit": limit, "count": count}, "items": users}
        )
    elif request.method == "POST":
        # check user permission
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        # validate request json
        try:
            request_json = request.get_json()
            validate(request_json, Users().schema)
        except ValidationError as error:
            raise errors.BadRequest(error.message)

        if Users().count({"username": request_json["username"]}):
            raise errors.BadRequest("Username is already taken.")

        if Users().count({"email": request_json["email"]}):
            raise errors.BadRequest("Email is already registered.")

        # generate password hash
        password = request_json.pop("password")
        request_json["password_hash"] = generate_password_hash(password)

        user_id = Users().insert_one(request_json).inserted_id
        return jsonify({"_id": user_id})


@blueprint.route("/<string:user_id>", methods=["PATCH"])
@authenticate
@only_for_roles(roles=Users.MANAGER_ROLE)
@bson_object_id(["user_id"])
def change_active_status(user_id: ObjectId, user: dict):
    request_json = request.get_json()

    new_status = request_json.get("active", None)
    if new_status is None:
        raise errors.BadRequest()

    user = Users().find_one({"_id": user_id}, {"active": 1})
    if user is None:
        raise errors.NotFound()

    Users().update_one(
        {"_id": ObjectId(user_id)}, {"$set": {"active": bool(new_status)}}
    )
    return jsonify({"_id": user_id})


@blueprint.route("/<string:user_id>", methods=["GET", "DELETE"])
@authenticate
@bson_object_id(["user_id"])
def document(user_id: ObjectId, user: dict):
    if request.method == "GET":
        # check user permission when not querying current user
        if not user_id == ObjectId(user["_id"]):
            ensure_user_matches_role(user, Users.MANAGER_ROLE)

        user = Users().find_one({"_id": user_id}, {"password_hash": 0})
        if user is None:
            raise errors.NotFound()

        return jsonify(user)
    elif request.method == "DELETE":
        # only manager can delete a user
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        deleted_count = Users().delete_one({"_id": user_id}).deleted_count
        if deleted_count == 0:
            raise errors.NotFound()

        return Response()


@blueprint.route("/<string:user_id>/password", methods=["PATCH"])
@authenticate
@bson_object_id(["user_id"])
def change_password(user_id: ObjectId, user: dict):
    # check user permission when not updating current user
    if not user_id == ObjectId(user["_id"]):
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

    request_json = request.get_json()

    # TODO: use json schema to validate
    password_old = request_json.get("old", None)
    password_new = request_json.get("new", None)
    if password_new is None or password_old is None:
        raise errors.BadRequest()

    user = Users().find_one({"_id": user_id}, {"password_hash": 1})
    if user is None:
        raise errors.NotFound()

    valid = check_password_hash(user["password_hash"], password_old)
    if not valid:
        raise errors.Unauthorized()

    Users().update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"password_hash": generate_password_hash(password_new)}},
    )
    return Response()
