from bson import ObjectId
from flask import Blueprint, request, jsonify, Response
from jsonschema import validate, ValidationError

from utils.mongo import Channels, Users
from . import (
    authenticate,
    bson_object_id,
    errors,
    ensure_user_matches_role,
    only_for_roles,
)


blueprint = Blueprint("channel", __name__, url_prefix="/channels")


@blueprint.route("/", methods=["GET", "POST"])
@authenticate
def collection(user: dict):
    """
    List or create channels
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
        channels = [channel for channel in Channels().find()]  # TODO: apply filters

        return jsonify({"meta": {"skip": skip, "limit": limit}, "items": channels})
    elif request.method == "POST":
        # check user permission
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        try:
            request_json = request.get_json()
            validate(request_json, Channels.schema)
        except ValidationError as error:
            raise errors.BadRequest(error.message)

        if Channels().count({"slug": request_json["slug"]}):
            raise errors.BadRequest("Channel with this slug exists.")

        channel_id = Channels().insert_one(request_json).inserted_id
        return jsonify({"_id": channel_id})


@blueprint.route("/<string:channel_id>", methods=["GET", "DELETE"])
@authenticate
@bson_object_id(["channel_id"])
def document(channel_id: ObjectId, user: dict):
    if request.method == "GET":
        # check user permission when not querying current user
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        channel = Channels().find_one({"_id": channel_id}, {})
        if channel is None:
            raise errors.NotFound()

        return jsonify(channel)
    elif request.method == "DELETE":
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        deleted_count = Channels().delete_one({"_id": channel_id}).deleted_count
        if deleted_count == 0:
            raise errors.NotFound()

        return Response()


@blueprint.route("/<string:channel_id>", methods=["PATCH"])
@authenticate
@only_for_roles(roles=Users.MANAGER_ROLE)
@bson_object_id(["channel_id"])
def change_active_status(channel_id: ObjectId, user: dict):
    # check user permission when not updating current user
    ensure_user_matches_role(user, Users.MANAGER_ROLE)

    request_json = request.get_json()

    new_status = request_json.get("active", None)
    if new_status is None:
        raise errors.BadRequest()

    channel = Channels().find_one({"_id": channel_id}, {"active": 1})
    if channel is None:
        raise errors.NotFound()

    Channels().update_one(
        {"_id": ObjectId(channel_id)}, {"$set": {"active": bool(new_status)}}
    )
    return jsonify({"_id": channel_id})
