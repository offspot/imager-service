import datetime
import os
from distutils.util import strtobool

import pymongo
from bson import ObjectId
from emailing import (
    send_order_created_email,
    send_order_failed_email,
    send_order_shipped_email,
)
from flask import Blueprint, jsonify, render_template, request
from jsonschema import ValidationError, validate
from utils.json import ensure_objectid
from utils.mongo import Orders, Users

from routes import authenticate, bson_object_id, errors, only_for_roles

blueprint = Blueprint("order", __name__, url_prefix="/orders")


def string_to_bool(string):
    return bool(strtobool(str(string)))


def create_order_from(payload):
    # validate payload
    validate(payload, Orders().schema)

    payload["status"] = Orders().created
    payload["tasks"] = {}
    payload["statuses"] = [
        {"status": Orders().created, "on": datetime.datetime.now(), "payload": None}
    ]

    # actually create Order
    order_id = Orders().insert_one(payload).inserted_id

    # define and record fname for this order
    if "fname" not in payload:
        fname = f"{order_id}.img"
    else:
        short_id = str(order_id)[:10]
        if "{rand}" in payload["fname"]:
            fname = payload["fname"].replace("{rand}", short_id)
        else:
            stem, ext = os.path.splitext(payload["fname"])
            fname = "".join((stem + f"_{short_id}", ext))
    Orders.update(order_id, {"fname": fname})

    # send email about new order
    send_order_created_email(order_id)

    # create creation task
    Orders.create_creator_task(order_id)

    return order_id


@blueprint.route("/", methods=["GET", "POST"])
@authenticate()
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

        query = {}
        projection = {"_id": 1}
        cursor = (
            Orders()
            .find(query, projection)
            .sort([("$natural", pymongo.DESCENDING)])
            .skip(skip)
            .limit(limit)
        )
        count = Orders().count_documents(query)
        orders = [Orders.get(order.get("_id")) for order in cursor]

        return jsonify(
            {"meta": {"skip": skip, "limit": limit, "count": count}, "items": orders}
        )
    if request.method == "POST":

        try:
            order_id = create_order_from(request.get_json())
        except ValidationError as error:
            raise errors.BadRequest(str(error))

        return jsonify({"_id": order_id})


@blueprint.route("/anonymize", methods=["PATCH"])
@authenticate()
@only_for_roles(roles=Users.MANAGER_ROLE)
def anonymize(user: dict):
    try:
        request_json = request.get_json()
        validate(request_json, {"order_ids": {"type": "list", "required": True}})
        order_ids = [ensure_objectid(oid) for oid in request_json.get("order_ids")]
    except ValidationError as error:
        raise errors.BadRequest(str(error))
    except Exception:
        raise errors.BadRequest("Orders IDs are not all valid IDs")

    try:
        Orders.anonymize(order_ids)
    except Exception:
        raise errors.NotFound()

    return jsonify({"_ids": order_ids})


@blueprint.route("/<string:order_id>", methods=["GET", "DELETE", "PATCH"])
@authenticate()
@only_for_roles(roles=Users.MANAGER_ROLE)
@bson_object_id(["order_id"])
def document(order_id: ObjectId, user: dict):
    """fetch indiviual order info or cancel it"""
    if request.method == "GET":
        with_logs = request.args.get("with_logs", default=False, type=string_to_bool)
        order = Orders.get_with_tasks(order_id, with_logs=with_logs)
        if order is None:
            raise errors.NotFound()

        return jsonify(order)

    if request.method == "PATCH":
        order = Orders.get_with_tasks(order_id)
        if order is None:
            raise errors.NotFound()

        request_json = request.get_json()
        Orders().add_shipment(order_id, request_json.get("shipment_details"))

        send_order_shipped_email(order_id)

        return jsonify(order)

    if request.method == "DELETE":
        # should prepare email message with infos from order here
        deleted_count = Orders().delete_one({"_id": order_id}).deleted_count
        if deleted_count == 0:
            raise errors.NotFound()

        # send email about deletion

        return jsonify({"_id": order_id})


@blueprint.route("/<string:order_id>/cancel", methods=["PATCH"])
@authenticate()
@only_for_roles(roles=Users.MANAGER_ROLE)
@bson_object_id(["order_id"])
def cancel(order_id: ObjectId, user: dict):
    order = Orders.get(order_id)
    if order is None:
        raise errors.NotFound()

    Orders().cancel(order_id)
    send_order_failed_email(order_id)

    return jsonify({"_id": order_id})


@blueprint.route("/<string:order_id>/add_shipment", methods=["GET", "POST"])
# @authenticate()
# @only_for_roles(roles=Users.WORKER_ROLES)
@bson_object_id(["order_id"])
def add_shipment(order_id: ObjectId):
    order = Orders().find_one({"_id": order_id, "status": Orders.pending_shipment})
    if order is None:
        raise errors.NotFound()

    if request.method == "GET":
        return render_template(
            "pub_add_shipment.html", order=order, order_id=order["_id"]
        )
    if request.method == "POST":
        shipment_details = request.form.get("details")
        if not shipment_details:
            raise errors.BadRequest("Missing shipment details")

        # store shipment details
        Orders().add_shipment(order_id, shipment_details)
        # refresh order object
        order = Orders.get(order_id)
        # send recipient an email
        send_order_shipped_email(order_id)

        return render_template(
            "pub_thank_shipment.html", order=order, order_id=order["_id"]
        )
