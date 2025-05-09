import pymongo
from bson import ObjectId
from flask import Blueprint, Response, jsonify, request
from flask import redirect as flask_redirect
from jsonschema import ValidationError, validate
from utils.mongo import AutoImages, Users
from utils.wasabi import get_autodelete_date_for

from routes import authenticate, ensure_user_matches_role, errors

blueprint = Blueprint("autoimage", __name__, url_prefix="/auto-images")


@blueprint.route("/", methods=["GET", "POST"])
@authenticate()
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
        with_config = request.args.get("with_config", default=False, type=bool)
        with_yaml = request.args.get("with_yaml", default=False, type=bool)
        skip = 0 if skip < 0 else skip
        limit = 20 if limit <= 0 else limit

        query = {}
        projection = {"config_yaml": 0, "config": 0}
        if with_config and with_yaml:
            projection = None
        elif with_config:
            projection = {"config_yaml": 0}
        elif with_yaml:
            projection = {"config": 0}
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


@blueprint.route("/<string:autoimage_slug>", methods=["GET", "PUT", "DELETE"])
@authenticate()
def document(autoimage_slug: ObjectId, user: dict):
    if request.method == "GET":
        # check user permission when not querying current user
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        # /!\ this returns nothing but the _id
        # seems like an error but it's useful at the moment since that endpoint
        # is called frequently to get autodelete_on so leaving as is.
        autoimage = AutoImages().find_one({"slug": autoimage_slug}, {})
        if autoimage is None:
            raise errors.NotFound()

        autoimage["autodelete_on"] = get_autodelete_date_for(autoimage_slug).isoformat()

        return jsonify(autoimage)

    # replacing autoimage without removing existing record
    elif request.method == "PUT":
        # check user permission
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        autoimage = AutoImages().find_one({"slug": autoimage_slug}, {})
        if autoimage is None:
            raise errors.NotFound()

        try:
            request_json = request.get_json()
            validate(request_json, AutoImages.update_schema)
        except ValidationError as error:
            raise errors.BadRequest(str(error))

        AutoImages().update_one({"slug": autoimage_slug}, {"$set": request_json})
        # we blank image status so periodic-tasks will recreate it
        AutoImages.update_status(autoimage_slug, status=None)
        return jsonify({"slug": request_json["slug"]})

    elif request.method == "DELETE":
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        deleted_count = AutoImages().delete_one({"slug": autoimage_slug}).deleted_count
        if deleted_count == 0:
            raise errors.NotFound()

        return Response()


@blueprint.route("/<string:autoimage_slug>/json", methods=["GET"])
@authenticate(allow_noauth=True)
def json_document(autoimage_slug: ObjectId, user: dict):

    autoimage = AutoImages().find_one(
        {"slug": autoimage_slug},
        {
            "slug": 1,
            "private": 1,
            "http_url": 1,
            "torrent_url": 1,
            "magnet_url": 1,
            "expire_on": 1,
            "_id": 0,
        },
    )
    if autoimage is None:
        raise errors.NotFound()

    if autoimage.pop("private", True):
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

    return jsonify(autoimage)


@blueprint.route("/<string:autoimage_slug>/redirect/<string:method>", methods=["GET"])
def redirect(autoimage_slug: ObjectId, method: str):
    """only for public images (user not forwarded)"""

    if method not in ["http", "torrent", "magnet"]:
        raise errors.NotFound()

    response = json_document(autoimage_slug)
    if response.status_code != 200:
        return response

    return flask_redirect(location=response.get_json()[f"{method}_url"], code=302)
