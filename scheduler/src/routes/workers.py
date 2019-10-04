import pymongo
from flask import Blueprint, request, jsonify
from jsonschema import ValidationError

from . import errors
from utils.mongo import Users, Acknowlegments
from . import authenticate, only_for_roles
from emailing import send_worker_sos_email


blueprint = Blueprint("worker", __name__, url_prefix="/workers")


@blueprint.route("/", methods=["GET"])
@authenticate
@only_for_roles(roles=Users.MANAGER_ROLE)
def collection(user: dict):

    skip = request.args.get("skip", default=0, type=int)
    limit = request.args.get("limit", default=20, type=int)
    skip = 0 if skip < 0 else skip
    limit = 20 if limit <= 0 else limit

    query = {}
    projection = None
    cursor = (
        Acknowlegments()
        .find(query, projection)
        .sort([("$natural", pymongo.ASCENDING)])
        .skip(skip)
        .limit(limit)
    )
    count = Acknowlegments().count_documents(query)
    workers = [worker for worker in cursor]

    return jsonify(
        {"meta": {"skip": skip, "limit": limit, "count": count}, "items": workers}
    )


@blueprint.route("/sos", methods=["POST"])
@authenticate
@only_for_roles(roles=Users.WORKER_ROLES)
def sos(user: dict):

    request_json = request.get_json()

    try:
        request_json = request.get_json()
        if "type" not in request_json:
            raise ValidationError("missing worker type")
    except ValidationError as error:
        raise errors.BadRequest(error.message)

    # update ACK
    aid, status_changed = Acknowlegments.sos_update(
        username=user["username"],
        worker_type=request_json.get("type"),
        slot=request.args.get("slot"),
        error=request_json.get("error"),
    )

    print("aid", aid, "changed", status_changed)

    # only email operator once
    if status_changed:
        send_worker_sos_email(aid)

    return jsonify({"_id": aid})
