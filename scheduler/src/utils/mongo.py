
import os
import datetime

from bson import ObjectId
from pymongo import MongoClient
from pymongo.database import Database as BaseDatabase
from pymongo.collection import Collection as BaseCollection


class Client(MongoClient):
    def __init__(self):
        super().__init__(host=os.getenv("MONGODB_URI", "mongo"))


class Database(BaseDatabase):
    def __init__(self):
        super().__init__(Client(), "Cardshop")


class Users(BaseCollection):
    MANAGER_ROLE = "manager"
    CREATOR_ROLE = "creator"
    WRITER_ROLE = "writer"
    WORKER_ROLES = [CREATOR_ROLE, WRITER_ROLE]
    ROLES = [MANAGER_ROLE, CREATOR_ROLE, WRITER_ROLE]
    RABBITMQ_ROLES = WORKER_ROLES + [MANAGER_ROLE]

    username = "username"
    email = "email"
    password_hash = "password_hash"
    scope = "scope"

    schema = {
        "username": {"type": "string", "regex": "^[a-zA-Z0-9_.+-]+$", "required": True},
        "email": {
            "type": "string",
            "regex": "^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        },
        "password_hash": {"type": "string", "required": True},
        "active": {"type": "boolean", "default": True, "required": True},
        "role": {"type": "string", "required": True},
        "scope": {
            "type": "dict",
            "required": True,
            "keyschema": {"type": "string"},
            "valueschema": {
                "type": "dict",
                "keyschema": {"type": "string"},
                "valueschema": {"type": "boolean"},
            },
        },
    }

    def __init__(self):
        super().__init__(Database(), "users")


class RefreshTokens(BaseCollection):
    def __init__(self):
        super().__init__(Database(), "refresh_tokens")


class Channels(BaseCollection):
    schema = {
        "slug": {"type": "string", "regex": "^[a-zA-Z0-9_.+-]+$", "required": True},
        "name": {"type": "string", "regex": "^.+$", "required": True},
        "active": {"type": "boolean", "default": True, "required": True},
        "private": {"type": "boolean", "default": False, "required": True},
    }

    def __init__(self):
        super().__init__(Database(), "channels")


class Warehouses(BaseCollection):
    schema = {
        "slug": {"type": "string", "regex": "^[a-zA-Z0-9_.+-]+$", "required": True},
        "upload_uri": {"type": "string", "regex": "^.+$", "required": True},
        "download_uri": {"type": "string", "regex": "^.+$", "required": True},
        "active": {"type": "boolean", "default": True, "required": True},
    }

    def __init__(self):
        super().__init__(Database(), "warehouses")


class Orders(BaseCollection):

    created = "created"
    pending_creator = "pending_creator"
    creating = "creating"
    creation_failed = "creation_failed"
    pending_writer = "pending_writer"
    writing = "writing"
    write_failed = "write_failed"
    written = "written"
    pending_shipment = "pending_shipment"
    shipped = "shipped"
    canceled = "canceled"
    failed = "failed"

    PENDING_STATUSES = [created, pending_creator, pending_writer, pending_shipment]
    WORKING_STATUSES = [creating, writing]
    FAILED_STATUSES = [creation_failed, write_failed, canceled, failed]
    SUCCESS_STATUSES = [shipped]

    schema = {
        "config": {"type": "dict", "required": True},
        "sd_card": {
            "type": "dict",
            "required": True,
            "schema": {
                "name": {"type": "string", "required": True},
                "size": {"type": "integer", "required": True},
            },
        },
        "quantity": {"type": "integer", "required": True},
        "units": {"type": "integer", "required": True},
        "client": {
            "type": "dict",
            "required": True,
            "schema": {
                "name": {"type": "string", "regex": "^.+$", "required": True},
                "email": {
                    "type": "string",
                    "regex": "^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
                    "required": True,
                },
            },
        },
        "recipient": {
            "type": "dict",
            "required": True,
            "schema": {
                "name": {"type": "string", "regex": "^.+$", "required": True},
                "email": {
                    "type": "string",
                    "regex": "^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
                    "required": False,
                },
                "phone": {"type": "string", "regex": "^\+?[0-9]+$", "required": False},
                "address": {"type": "string", "required": True},
                "country": {"type": "string", "required": True},
                "shipment": {"type": "string", "required": False, "nullable": True},
            },
        },
        "channel": {"type": "string", "required": True},
        "statuses": {"type": "list", "required": False},
        "logs": {"type": "list", "required": False},
        "tasks": {"type": "dict", "required": False},
    }

    def __init__(self):
        super().__init__(Database(), "orders")

    @classmethod
    def get(cls, order_id, projection={"logs": 0}):
        return cls().find_one({"_id": order_id}, projection)

    @classmethod
    def get_with_tasks(cls, order_id, projection={"logs": 0}):
        order = cls().find_one({"_id": order_id}, projection)
        if "creation" in order.get("tasks", {}).keys():
            order["tasks"]["creation"] = CreatorTasks.get(
                order["tasks"]["creation"],
                {"worker": 1, "statuses": 1, "_id": 1, "logs": 1},
            )
        if "writing" in order.get("tasks", {}).keys():
            order["tasks"]["writing"] = CreatorTasks.get(
                order["tasks"]["writing"],
                {"worker": 1, "statuses": 1, "_id": 1, "logs": 1},
            )
        return order

    @classmethod
    def create_creator_task(cls, order_id):
        order = cls.get(order_id)
        if order is None:
            raise ValueError("Order #{} not exists. can't create task".format(order_id))

        payload = {
            "order": order_id,
            "channel": order["channel"],
            "upload_uri": order["warehouse"]["upload_uri"],
            "worker": None,
            "config": order["config"],
            "size": order["sd_card"]["size"],
            "logs": {"worker": None, "installer": None},
            "status": CreatorTasks.pending,
            "statuses": [
                {"status": CreatorTasks.pending, "on": datetime.datetime.now()}
            ],
        }
        task_id = CreatorTasks().insert_one(payload).inserted_id

        # add task_id to order
        cls().update_one(
            {"_id": ObjectId(order_id)}, {"$set": {"tasks.creation": task_id}}
        )

        return task_id


class Tasks(BaseCollection):
    @classmethod
    def get(cls, task_id, projection=None):
        return cls().find_one({"_id": task_id}, projection)

    @classmethod
    def update_logs(cls, task_id, worker_log=None, installer_log=None):
        if worker_log is None and installer_log is None:
            return
        update = {}
        if worker_log is not None:
            update = {"logs.worker": worker_log}
        if installer_log is not None:
            update = {"logs.installer": installer_log}

        cls().update_one({"_id": ObjectId(task_id)}, {"$set": update})

    @classmethod
    def update_status(cls, task_id, status, payload=None, extra_update={}):
        task = cls.get(task_id)
        statuses = task["statuses"]
        statuses.append(
            {"status": status, "on": datetime.datetime.now(), "payload": payload}
        )
        update = {"status": status, "statuses": statuses}
        update.update(extra_update)
        cls().update_one({"_id": ObjectId(task_id)}, {"$set": update})

    @classmethod
    def register(cls, task_id, worker):
        cls.update_status(
            task_id=task_id,
            status=cls.received,
            extra_update={"worker": worker},
            payload="assigned worker: {}".format(worker["username"]),
        )

    @classmethod
    def find_availables(cls, channel):
        tasks = [
            cls.get(task.get("_id"))
            for task in cls().find({"status": cls.pending}, {"_id": 1})
        ]
        return tasks


class CreatorTasks(Tasks):

    pending = "pending"
    received = "received"
    building = "building"
    failed_to_build = "failed_to_build"
    built = "built"
    uploading = "uploading"
    failed_to_upload = "failed_to_upload"
    uploaded = "uploaded"
    failed = "failed"
    canceled = "canceled"
    timedout = "timedout"

    PENDING_STATUSES = [pending]
    WORKING_STATUSES = [received, building, built, uploading]
    FAILED_STATUSES = [failed_to_build, failed_to_upload, failed, canceled, timedout]
    SUCCESS_STATUSES = [uploaded]

    schema = {
        "order": {"type": "string", "required": True},
        "channel": {"type": "string", "required": True, "nullable": True},
        "worker": {"type": "string", "required": True, "nullable": True},
        "config": {"type": "dict", "required": True},
        "size": {"type": "integer", "required": True},
        "logs": {"type": "dict"},
        "status": {"type": "string", "required": True},
        "statuses": {"type": "list"},
    }

    def __init__(self):
        super().__init__(Database(), "creator_tasks")


class WriterTasks(Tasks):

    pending = "pending"
    received = "received"
    downloading = "downloading"
    failed_to_download = "failed_to_download"
    downloaded = "downloaded"
    waiting_for_card = "waiting_for_card"
    writing = "writing"
    failed_to_write = "failed_to_write"
    written = "written"
    failed = "failed"
    canceled = "canceled"
    timedout = "timedout"

    PENDING_STATUSES = [pending]
    WORKING_STATUSES = [received, downloading, downloaded, writing]
    FAILED_STATUSES = [failed_to_download, failed_to_write, failed, canceled, timedout]
    SUCCESS_STATUSES = [written]

    schema = {
        "order": {"type": "string", "required": True},
        "channel": {"type": "string", "required": True, "nullable": True},
        "worker": {"type": "string", "required": True, "nullable": True},
        "name": {"type": "string", "regex": "^.+$", "required": True},
        "image_url": {"type": "string", "required": True},
        "image_checksum": {"type": "string", "required": True},
        "image_size": {"type": "integer", "required": True},  # bytes
        "sd_size": {"type": "integer", "required": True},
        "logs": {"type": "list"},
        "status": {"type": "string", "required": True},
        "statuses": {"type": "list"},
    }

    def __init__(self):
        super().__init__(Database(), "writer_tasks")
