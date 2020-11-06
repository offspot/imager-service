import datetime

import pymongo
from flask import Blueprint, request, jsonify
from jsonschema import ValidationError

from . import errors
from . import authenticate, only_for_roles
from emailing import send_worker_sos_email
from utils.mongo import Users, Acknowlegments, CreatorTasks, Orders


blueprint = Blueprint("worker", __name__, url_prefix="/workers")


@blueprint.route("/", methods=["GET"])
@authenticate()
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
@authenticate()
@only_for_roles(roles=Users.WORKER_ROLES)
def sos(user: dict):

    request_json = request.get_json()

    try:
        request_json = request.get_json()
        if "type" not in request_json:
            raise ValidationError("missing worker type")
    except ValidationError as error:
        raise errors.BadRequest(str(error))

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


@blueprint.route("/load", methods=["GET"])
@authenticate()
@only_for_roles(roles=Users.MANAGER_ROLE)
def calculate_load(user: dict):

    now = datetime.datetime.now()

    def is_connected(worker):
        """ whether a worker is considered connected (ping 15mn ago) """
        try:
            dt = datetime.datetime.fromisoformat(worker["on"].replace("Z", "")) - now
            return dt.total_seconds <= 900  # 10mn
        except Exception:
            return False

    def get_remaining_minutes(task):
        """ estimated remaining duration of task based on units and when/if started """
        # physical card units are 10 times download ones but creator impact is identical
        units = task["units"] / 10 if task["units"] > 512 else task["units"]

        # small images are done in about an hour
        # larger one increase duration with size ; especially due to upload
        duration = max(int(units * 1.875), 90) if units >= 32 else 60
        if task["status"] in ["pending", "received"]:
            # task has not started
            return duration

        # already started, remove spent time from received
        for event in task["events"]:
            if event["status"] == "received":
                passed = datetime.datetime.now() - datetime.datetime.fromisoformat(
                    event["on"].replace("Z", "")
                )
                return duration - (passed.total_seconds // 60)

        # couldn't find received ; returning full duration
        return duration

    # get number of online workers
    cursor = Acknowlegments().find({}, None).sort([("$natural", pymongo.ASCENDING)])
    nb_connected_workers = len(
        [
            worker
            for worker in cursor
            if worker.get("worker_type") == "creator" and is_connected(worker)
        ]
    )

    # get list of pending task and calculate remaining durations for those
    tasks = []
    for task in CreatorTasks().find(
        {"status": {"$in": ["pending", "received", "building", "built", "uploading"]}},
        {"status": 1, "events": 1, "order": 1, "worker": 1},
    ):
        task["units"] = Orders().find_one({"_id": task["order"]}, {"units": 1})["units"]
        task["duration"] = get_remaining_minutes(task)
        tasks.append(task)
    nb_pending_taks = len(tasks)

    cumulative_duration = sum(task["duration"] for task in tasks)
    remaining_minutes = (
        cumulative_duration // nb_connected_workers if nb_connected_workers else None
    )
    estimated_completion = (
        now + datetime.timedelta(total_seconds=remaining_minutes * 60)
        if remaining_minutes
        else None
    )

    return jsonify(
        {
            "connected_workers": nb_connected_workers,
            "pending_tasks": nb_pending_taks,
            "cumulative_duration": cumulative_duration,
            "remaining_minutes": remaining_minutes,
            "estimated_completion": estimated_completion.isoformat()
            if estimated_completion
            else None,
        }
    )
