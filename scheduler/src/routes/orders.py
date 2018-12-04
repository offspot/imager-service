
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

        orders = [
            Orders.get(order.get("_id")) for order in Orders().find({}, {"_id": 1})
        ]

        return jsonify({"meta": {"skip": skip, "limit": limit}, "items": orders})
    elif request.method == "POST":

        # validate request json
        try:
            request_json = request.get_json()
            validate(request_json, Orders().schema)
        except ValidationError as error:
            raise errors.BadRequest(error.message)

        request_json["status"] = Orders().created
        request_json["tasks"] = {}
        request_json["statuses"] = [
            {"status": Orders().created, "on": datetime.datetime.now(), "payload": None}
        ]

        # actually create Ordr
        order_id = Orders().insert_one(request_json).inserted_id
        print("ORDER_ID", order_id)

        # send email about new order
        send_order_created_email(order_id)

        # create creation task
        Orders.create_creator_task(order_id)

        return jsonify({"_id": order_id})


@blueprint.route("/<string:order_id>", methods=["GET", "DELETE"])
@authenticate
@only_for_roles(roles=Users.MANAGER_ROLE)
@bson_object_id(["order_id"])
def document(order_id: ObjectId, user: dict):
    """ fetch indiviual order info or cancel it """
    if request.method == "GET":
        order = Orders.get_with_tasks(order_id)
        if order is None:
            raise errors.NotFound()

        return jsonify(order)

    elif request.method == "DELETE":
        # TODO: prepare email message with infos from order
        deleted_count = Orders().delete_one({"_id": order_id}).deleted_count
        if deleted_count == 0:
            raise errors.NotFound()

        # send email about deletion

        return jsonify({"_id": order_id})
