import pymongo
from bson import ObjectId
from flask import Blueprint, request, jsonify, Response, redirect as flask_redirect
from jsonschema import validate, ValidationError

from utils.mongo import AutoImages, Users
from . import (
    authenticate,
    errors,
    ensure_user_matches_role,
    only_for_roles,
)


blueprint = Blueprint("autoimage", __name__, url_prefix="/auto-images")


@blueprint.route("/", methods=["GET", "POST"])
@authenticate
def collection(user: dict):
    """
    List or create autoimage
    """

    if request.method == "GET":
        # check user permission
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        # unpack url parameters
        skip = request.args.get("skip", default=0, type=int)
        limit = request.args.get("limit", default=20, type=int)
        skip = 0 if skip < 0 else skip
        limit = 20 if limit <= 0 else limit

        query = {}
        projection = None
        cursor = (
            AutoImages()
            .find(query, projection)
            .sort([("$natural", pymongo.ASCENDING)])
            .skip(skip)
            .limit(limit)
        )
        count = AutoImages().count_documents(query)
        autoimages = [autoimage for autoimage in cursor]

        return jsonify(
            {
                "meta": {"skip": skip, "limit": limit, "count": count},
                "items": autoimages,
            }
        )
    elif request.method == "POST":
        # check user permission
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        try:
            request_json = request.get_json()
            validate(request_json, AutoImages.schema)
        except ValidationError as error:
            raise errors.BadRequest(str(error))

        if AutoImages().count({"slug": request_json["slug"]}):
            raise errors.BadRequest("autoimage with this slug exists.")

        AutoImages().insert_one(request_json)
        return jsonify({"slug": request_json["slug"]})


@blueprint.route("/<string:autoimage_slug>", methods=["GET", "DELETE"])
@authenticate
def document(autoimage_slug: ObjectId, user: dict):
    if request.method == "GET":
        # check user permission when not querying current user
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        autoimage = AutoImages().find_one({"slug": autoimage_slug}, {})
        if autoimage is None:
            raise errors.NotFound()

        return jsonify(autoimage)
    elif request.method == "DELETE":
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        deleted_count = AutoImages().delete_one({"slug": autoimage_slug}).deleted_count
        if deleted_count == 0:
            raise errors.NotFound()

        return Response()


@blueprint.route("/<string:autoimage_slug>/json", methods=["GET"])
def json_document(autoimage_slug: ObjectId):

    autoimage = AutoImages().find_one(
        {"slug": autoimage_slug}, {"slug": 1, "url": 1, "expire_on": 1, "_id": 0}
    )
    if autoimage is None:
        raise errors.NotFound()

    return jsonify(autoimage)


@blueprint.route("/<string:autoimage_slug>/redirect", methods=["GET"])
def redirect(autoimage_slug: ObjectId):

    response = json_document(autoimage_slug)
    if response.status_code != 200:
        return response

    return flask_redirect(location=response.get_json()["url"], code=302)


@blueprint.route("/<string:autoimage_slug>", methods=["PATCH"])
@authenticate
@only_for_roles(roles=Users.MANAGER_ROLE)
def change_active_status(autoimage_slug: ObjectId, user: dict):
    # check user permission when not updating current user
    ensure_user_matches_role(user, Users.MANAGER_ROLE)

    request_json = request.get_json()

    new_status = request_json.get("active", None)
    if new_status is None:
        raise errors.BadRequest()

    autoimage = AutoImages().find_one({"slug": autoimage_slug}, {"active": 1})
    if autoimage is None:
        raise errors.NotFound()

    AutoImages().update_one(
        {"slug": ObjectId(autoimage_slug)}, {"$set": {"active": bool(new_status)}}
    )
    return jsonify({"slug": autoimage_slug})
