#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging
from bson import ObjectId
from flask import Blueprint, request, jsonify, Response, render_template

from utils.mongo import (
    CreatorTasks,
    WriterTasks,
    DownloaderTasks,
    Users,
    Tasks,
    Orders,
    Acknowlegments,
)
from . import authenticate, bson_object_id, errors, only_for_roles
from emailing import (
    send_image_uploaded_email,
    send_insert_card_email,
    send_image_writing_email,
    send_image_written_email,
    send_order_failed_email,
    send_order_pending_shipment_email,
)


blueprint = Blueprint("task", __name__, url_prefix="/tasks")


# def tasks_cls_for(user):
#     return CreatorTasks if user["role"] == Users.CREATOR_ROLE else WriterTasks


def tasks_cls_for(task_type):
    cls = {
        "creator": CreatorTasks,
        "downloader": DownloaderTasks,
        "writer": WriterTasks,
    }.get(task_type)
    if cls is None:
        raise errors.NotFound("Incorrect task type")
    return cls


@blueprint.route("/<string:task_type>", methods=["GET"])
@authenticate
@only_for_roles(roles=Users.WORKER_ROLES)
def typed_collection(task_type: str, user: dict):
    if request.method == "GET":
        Acknowlegments.idle_update(
            username=user["username"],
            worker_type=task_type,
            slot=request.args.get("slot"),
        )
        tasks = tasks_cls_for(task_type).find_availables(channel=user.get("channel"))

        return jsonify(tasks)


@blueprint.route("/<string:task_type>/<string:task_id>", methods=["GET", "DELETE"])
@authenticate
@only_for_roles(roles=Users.WORKER_ROLES)
@bson_object_id(["task_id"])
def document(task_id: ObjectId, task_type: str, user: dict):
    """ fetch indiviual yask info or cancel it """
    if request.method == "GET":
        task = tasks_cls_for(task_type).get(task_id)
        if task is None:
            raise errors.NotFound()

        return jsonify(task)

    elif request.method == "DELETE":
        # TODO: prepare email message with infos from order
        task_cls = tasks_cls_for(task_type)
        deleted_count = task_cls().delete_one({"_id": task_id}).deleted_count
        if deleted_count == 0:
            raise errors.NotFound()

        # send email about deletion

        return jsonify({"_id": task_id})


@blueprint.route("/<string:task_type>/<string:task_id>/request", methods=["PATCH"])
@authenticate
@only_for_roles(roles=Users.WORKER_ROLES)
@bson_object_id(["task_id"])
def register_task(task_id: ObjectId, task_type: str, user: dict):
    task_cls = tasks_cls_for(task_type)
    task = task_cls().find({"_id": task_id, "status": task_cls.pending})
    if task is None:
        raise errors.NotFound()

    task_cls.register(task_id, user)

    # update ACK
    Acknowlegments.busy_update(
        username=user["username"],
        worker_type=task_type,
        slot=request.args.get("slot"),
        task_id=task_id,
    )

    return jsonify({"_id": task_id})


@blueprint.route(
    "/<string:task_type>/<string:task_id>/confirm_inserted", methods=["GET"]
)
# @authenticate
# @only_for_roles(roles=Users.WORKER_ROLES)
@bson_object_id(["task_id"])
def confirm_inserted_task(task_id: ObjectId, task_type: str):
    task_cls = tasks_cls_for(task_type)
    task = task_cls().find_one({"_id": task_id, "status": task_cls.waiting_for_card})
    if task is None:
        raise errors.NotFound()

    task_cls.update_status(task_id, status=task_cls.card_inserted)
    task_cls.cascade_status(task_id, task_cls.card_inserted)

    order = Orders().get(task["order"])

    return render_template("pub_thank_inserted.html", order=order, task=task)


@blueprint.route("/<string:task_type>/<string:task_id>/status", methods=["PATCH"])
@authenticate
@only_for_roles(roles=Users.WORKER_ROLES)
@bson_object_id(["task_id"])
def update_status(task_id: ObjectId, task_type: str, user: dict):
    task_cls = tasks_cls_for(task_type)
    task = task_cls().get(task_id)
    if task is None:
        raise errors.NotFound()

    request_json = request.get_json()
    # try:
    #     request_json = request.get_json()
    #     validate(request_json, Orders().schema)
    # except ValidationError as error:
    #     raise errors.BadRequest(error.message)

    # update task status
    status = request_json.get("status")
    task_cls.update_status(
        task_id,
        status=request_json.get("status"),
        payload=request_json.get("log"),
        extra_update=request_json.get("extra"),
    )

    # update order status based on this task
    task_cls.cascade_status(task_id, request_json.get("status"))

    # send email if appropriate
    order_id = task["order"]

    # create task uploaded image
    if status == Tasks.uploaded:
        send_image_uploaded_email(order_id)

        # create DownloadTask
        Orders().create_downloader_task(
            order_id,
            {
                "fname": task.get("image", {}).get("fname"),
                "size": task.get("image", {}).get("size"),
                "checksum": task.get("image", {}).get("checksum"),
            },
        )

    # download task downloaded image
    elif status == Tasks.downloaded:
        # create WriterTask(s)
        Orders().create_writer_tasks(order_id)

    # write task was registered
    elif status == Tasks.waiting_for_card:
        # send email to insert card
        send_insert_card_email(order_id, task_id)

    # write task started writing
    elif status == Tasks.writing:
        send_image_writing_email(order_id, task_id)

    # write task completed
    elif status == Tasks.written:
        send_image_written_email(order_id, task_id)

        order = Orders().get_with_tasks(order_id)
        # all write tasks are marked as written
        if not [1 for wt in order["tasks"]["write"] if wt["status"] != Tasks.written]:
            Orders().update_status(order_id, Orders.pending_shipment)

            send_order_pending_shipment_email(order_id)

            # find matching download task and mark it for file removal
            DownloaderTasks().update_status(
                task_id=order["tasks"]["download"]["_id"],
                status=Tasks.pending_image_removal,
            )

    elif status in Tasks.FAILED_STATUSES:
        send_order_failed_email(order_id)

    return jsonify({"_id": task_id})


@blueprint.route("/<string:task_type>/<string:task_id>/logs", methods=["POST"])
@authenticate
@only_for_roles(roles=Users.WORKER_ROLES)
@bson_object_id(["task_id"])
def add_log(task_id: ObjectId, task_type: str, user: dict):
    task_cls = tasks_cls_for(task_type)
    task = task_cls().get(task_id)
    if task is None:
        raise errors.NotFound()

    request_json = request.get_json()

    task_cls.update_logs(
        task_id,
        worker_log=request_json.get("worker_log"),
        installer_log=request_json.get("installer_log"),
        uploader_log=request_json.get("uploader_log"),
        downloader_log=request_json.get("downloader_log"),
        wipe_log=request_json.get("wipe_log"),
        writer_log=request_json.get("writer_log"),
    )

    # update ACK
    Acknowlegments.busy_update(
        username=user["username"],
        worker_type=task_type,
        slot=request.args.get("slot"),
        task_id=task_id,
    )

    return jsonify({"_id": task_id})
