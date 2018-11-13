
import datetime

from bson import ObjectId
from flask import Blueprint, request, jsonify, Response

from utils.mongo import CreatorTasks, WriterTasks, Users
from . import authenticate, bson_object_id, errors, only_for_roles


blueprint = Blueprint("task", __name__, url_prefix="/tasks")


def tasks_cls_for(user):
    return CreatorTasks if user["role"] == Users.CREATOR_ROLE else WriterTasks


@blueprint.route("/", methods=["GET"])
@authenticate
@only_for_roles(roles=Users.WORKER_ROLES)
def collection(user: dict):
    """ list of tasks that are relevant to user """

    if request.method == "GET":
        tasks = tasks_cls_for(user).find_availables(channel=user.get("channel"))

        return jsonify(tasks)


@blueprint.route("/<string:task_id>", methods=["GET", "DELETE"])
@authenticate
@only_for_roles(roles=Users.WORKER_ROLES)
@bson_object_id(["task_id"])
def document(task_id: ObjectId, user: dict):
    """ fetch indiviual yask info or cancel it """
    if request.method == "GET":
        task = tasks_cls_for(user).get(task_id)
        if task is None:
            raise errors.NotFound()

        return jsonify(task)

    elif request.method == "DELETE":
        # TODO: prepare email message with infos from order
        task_cls = tasks_cls_for(user)
        deleted_count = task_cls().delete_one({"_id": task_id}).deleted_count
        if deleted_count == 0:
            raise errors.NotFound()

        # send email about deletion

        return jsonify({"_id": task_id})


@blueprint.route("/<string:task_id>/request", methods=["PATCH"])
@authenticate
@only_for_roles(roles=Users.WORKER_ROLES)
@bson_object_id(["task_id"])
def register_task(task_id: ObjectId, user: dict):
    task_cls = tasks_cls_for(user)
    task = task_cls().find({"_id": task_id, "status": task_cls.pending})
    if task is None:
        raise errors.NotFound()

    task_cls.register(task_id, user)

    return jsonify({"_id": task_id})


@blueprint.route("/<string:task_id>/status", methods=["PATCH"])
@authenticate
@only_for_roles(roles=Users.WORKER_ROLES)
@bson_object_id(["task_id"])
def update_status(task_id: ObjectId, user: dict):
    task_cls = tasks_cls_for(user)
    task = task_cls().get(task_id)
    if task is None:
        raise errors.NotFound()

    request_json = request.get_json()
    # try:
    #     request_json = request.get_json()
    #     validate(request_json, Orders().schema)
    # except ValidationError as error:
    #     raise errors.BadRequest(error.message)

    task_cls.update_status(
        task_id, status=request_json.get("status"), payload=request_json.get("log")
    )

    return jsonify({"_id": task_id})


@blueprint.route("/<string:task_id>/logs", methods=["POST"])
@authenticate
@only_for_roles(roles=Users.WORKER_ROLES)
@bson_object_id(["task_id"])
def add_log(task_id: ObjectId, user: dict):
    task_cls = tasks_cls_for(user)
    task = task_cls().get(task_id)
    if task is None:
        raise errors.NotFound()

    request_json = request.get_json()

    task_cls.update_logs(
        task_id,
        worker_log=request_json.get("worker_log"),
        installer_log=request_json.get("installer_log"),
    )

    return jsonify({"_id": task_id})
