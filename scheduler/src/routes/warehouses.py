import pymongo
from bson import ObjectId
from flask import Blueprint, Response, jsonify, request
from jsonschema import ValidationError, validate
from utils.mongo import Users, Warehouses

from routes import (
    authenticate,
    bson_object_id,
    ensure_user_matches_role,
    errors,
    only_for_roles,
)

blueprint = Blueprint("warehouse", __name__, url_prefix="/warehouses")


@blueprint.route("/", methods=["GET", "POST"])
@authenticate()
def collection(user: dict):
    """
    List or create warehouses
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
            Warehouses()
            .find(query, projection)
            .sort([("$natural", pymongo.ASCENDING)])
            .skip(skip)
            .limit(limit)
        )
        count = Warehouses().count_documents(query)
        warehouses = [warehouse for warehouse in cursor]

        return jsonify(
            {
                "meta": {"skip": skip, "limit": limit, "count": count},
                "items": warehouses,
            }
        )
    elif request.method == "POST":
        # check user permission
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        try:
            request_json = request.get_json()
            validate(request_json, Warehouses.schema)
        except ValidationError as error:
            raise errors.BadRequest(error.message)

        if Warehouses().count({"slug": request_json["slug"]}):
            raise errors.BadRequest("Warehouse with this slug exists.")

        warehouse_id = Warehouses().insert_one(request_json).inserted_id
        return jsonify({"_id": warehouse_id})


@blueprint.route("/<string:warehouse_slug>", methods=["GET", "DELETE"])
@authenticate()
def document(warehouse_slug: ObjectId, user: dict):
    if request.method == "GET":
        # check user permission when not querying current user
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        warehouse = Warehouses().find_one({"slug": warehouse_slug})
        if warehouse is None:
            raise errors.NotFound()

        return jsonify(warehouse)
    elif request.method == "DELETE":
        ensure_user_matches_role(user, Users.MANAGER_ROLE)

        deleted_count = Warehouses().delete_one({"slug": warehouse_slug}).deleted_count
        if deleted_count == 0:
            raise errors.NotFound()

        return Response()


@blueprint.route("/<string:warehouse_id>", methods=["PATCH"])
@authenticate()
@only_for_roles(roles=Users.MANAGER_ROLE)
@bson_object_id(["warehouse_id"])
def change_active_status(warehouse_id: ObjectId, user: dict):
    # check user permission when not updating current user
    ensure_user_matches_role(user, Users.MANAGER_ROLE)

    request_json = request.get_json()

    new_status = request_json.get("active", None)
    if new_status is None:
        raise errors.BadRequest()

    warehouse = Warehouses().find_one({"_id": warehouse_id}, {"active": 1})
    if warehouse is None:
        raise errors.NotFound()

    Warehouses().update_one(
        {"_id": ObjectId(warehouse_id)}, {"$set": {"active": bool(new_status)}}
    )
    return jsonify({"_id": warehouse_id})
