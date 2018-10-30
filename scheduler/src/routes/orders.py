
import datetime
from bson import ObjectId
from flask import Blueprint, request, jsonify, Response
from jsonschema import validate, ValidationError

from utils.mongo import Orders, Users
from emailing import send_order_created_email
from . import authenticate, bson_object_id, errors, only_for_roles


blueprint = Blueprint("order", __name__, url_prefix="/orders")


@blueprint.route("/", methods=["GET", "POST"])
@authenticate
@only_for_roles(roles=Users.MANAGER_ROLE)
def collection(user: dict):
    """
    List or create orders
    """

    if request.method == "GET":
        # unpack url parameters
        skip = request.args.get("skip", default=0, type=int)
        limit = request.args.get("limit", default=20, type=int)
        skip = 0 if skip < 0 else skip
        limit = 20 if limit <= 0 else limit

        orders = [order for order in Orders().find({})]

        return jsonify({"meta": {"skip": skip, "limit": limit}, "items": orders})
    elif request.method == "POST":

        # validate request json
        try:
            request_json = request.get_json()
            validate(request_json, Orders().schema)
        except ValidationError as error:
            raise errors.BadRequest(error.message)

        request_json["statuses"] = [{"status": Orders().created,
                                     "on": datetime.datetime.now(),
                                     "payload": None}]

        order_id = Orders().insert_one(request_json).inserted_id

        # send email about new order
        send_order_created_email(order_id)
        return jsonify({"_id": order_id})


@blueprint.route("/<string:order_id>", methods=["GET", "DELETE"])
@authenticate
@only_for_roles(roles=Users.MANAGER_ROLE)
@bson_object_id(["order_id"])
def document(order_id: ObjectId, user: dict):
    """ fetch indiviual order info or cancel it """
    if request.method == "GET":
        order = Orders().find_one({"_id": order_id}, {"logs": 0})
        if order is None:
            raise errors.NotFound()

        return jsonify(order)

    elif request.method == "DELETE":
        deleted_count = Orders().delete_one({"_id": order_id}).deleted_count
        if deleted_count == 0:
            raise errors.NotFound()

        return Response()

@blueprint.route("/<string:order_id>/status", methods=["PATCH"])
@authenticate
@only_for_roles(roles=Users.WORKER_ROLES)
@bson_object_id(["order_id"])
def update_status(order_id: ObjectId, user: dict):
    # {"status": "XXX", "on": datetime, "payload": "XXX"}
    pass


@blueprint.route("/<string:order_id>/logs", methods=["POST"])
@authenticate
@only_for_roles(roles=Users.WORKER_ROLES)
@bson_object_id(["order_id"])
def add_log(order_id: ObjectId, user: dict):
    # log_type, on, log_content
    pass
