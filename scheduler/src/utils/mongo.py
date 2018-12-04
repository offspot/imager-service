
import os
import datetime

from bson import ObjectId
from pymongo import MongoClient
from pymongo.database import Database as BaseDatabase
from pymongo.collection import Collection as BaseCollection

from utils.json import ensure_objectid


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

    schema = {
        "username": {"type": "string", "regex": "^[a-zA-Z0-9_.+-]+$", "required": True},
        "email": {
            "type": "string",
            "regex": "^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        },
        "password_hash": {"type": "string", "required": True},
        "active": {"type": "boolean", "default": True, "required": True},
        "role": {"type": "string", "required": True},
    }

    def __init__(self):
        super().__init__(Database(), "users")

    @classmethod
    def by_username(cls, username):
        return cls().find_one({"username": username})


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
    downloading = "downloading"
    download_failed = "download_failed"
    downloaded = "downloaded"
    writing = "writing"
    write_failed = "write_failed"
    written = "written"
    pending_shipment = "pending_shipment"
    shipped = "shipped"
    canceled = "canceled"
    failed = "failed"

    PENDING_STATUSES = [created, pending_creator, pending_writer, pending_shipment]
    WORKING_STATUSES = [creating, downloading, writing]
    FAILED_STATUSES = [creation_failed, download_failed, write_failed, canceled, failed]
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
        order = cls().find_one(
            {"_id": ensure_objectid(order_id)}, projection=projection
        )
        if order is None:
            raise ValueError(
                "Unable to find/retrieve object with ID {}".format(order_id)
            )
        return order

    @classmethod
    def get_tasks(cls, order_id):
        order = cls().get(order_id, {"tasks": 1})
        return {
            "create": CreatorTasks().get(order["tasks"].get("create")),
            "download": DownloaderTasks().get(order["tasks"].get("download")),
            "write": [
                WriterTasks().get(task) for task in order["tasks"].get("write", [])
            ],
        }

    @classmethod
    def get_with_tasks(cls, order_id, projection={"logs": 0}):
        order = cls().get(order_id, projection=projection)
        order["tasks"].update(cls().get_tasks(order_id))
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
            "logs": {"worker": None, "installer": None, "uploader": None},
            "status": CreatorTasks.pending,
            "statuses": [
                {"status": CreatorTasks.pending, "on": datetime.datetime.now()}
            ],
        }
        task_id = CreatorTasks().insert_one(payload).inserted_id

        # add task_id to order
        cls().update_one(
            {"_id": ObjectId(order_id)}, {"$set": {"tasks.create": task_id}}
        )

        return task_id

    @classmethod
    def create_downloader_task(cls, order_id, upload_details):
        order = cls.get(order_id)
        if order is None:
            raise ValueError("Order #{} not exists. can't create task".format(order_id))

        payload = {
            "order": order_id,
            "channel": order["channel"],
            "download_uri": order["warehouse"]["download_uri"],
            "worker": None,
            "image_fname": upload_details.get("fname"),
            "image_checksum": upload_details.get("checksum"),
            "image_size": upload_details.get("size"),
            "logs": {"worker": None, "downloader": None},
            "status": DownloaderTasks.pending,
            "statuses": [
                {"status": DownloaderTasks.pending, "on": datetime.datetime.now()}
            ],
        }
        task_id = DownloaderTasks().insert_one(payload).inserted_id

        # add task_id to order
        cls().update_one(
            {"_id": ObjectId(order_id)}, {"$set": {"tasks.download": task_id}}
        )

        return task_id

    @classmethod
    def create_writer_tasks(cls, order_id):
        order = cls.get_with_tasks(order_id)
        if order is None:
            raise ValueError("Order #{} not exists. can't create task".format(order_id))

        payload = {
            "order": order_id,
            "channel": order["channel"],
            "worker": order["tasks"]["download"]["worker"],
            "image_fname": order["tasks"]["download"]["image_fname"],
            "image_checksum": order["tasks"]["download"]["image_checksum"],
            "image_size": order["tasks"]["download"]["image_size"],
            "logs": {"worker": None, "downloader": None},
            "status": DownloaderTasks.pending,
            "statuses": [
                {"status": DownloaderTasks.pending, "on": datetime.datetime.now()}
            ],
        }

        task_ids = []
        for index in range(0, order["quantity"]):
            task_ids.append(WriterTasks().insert_one(payload).inserted_id)

        # add task_id to order
        cls().update_one(
            {"_id": ObjectId(order_id)}, {"$set": {"tasks.write": task_ids}}
        )

        return task_ids

    @classmethod
    def update_status(cls, order_id, status, payload=None, extra_update={}):
        order = cls.get(order_id)
        # don't update if still current status
        if status == order["status"]:
            return
        statuses = order["statuses"]
        statuses.append(
            {"status": status, "on": datetime.datetime.now(), "payload": payload}
        )
        update = {"status": status, "statuses": statuses}
        update.update(extra_update)
        cls().update_one({"_id": ObjectId(order_id)}, {"$set": update})


class Tasks(BaseCollection):

    pending = "pending"
    received = "received"

    # create
    building = "building"
    failed_to_build = "failed_to_build"
    built = "built"
    uploading = "uploading"
    failed_to_upload = "failed_to_upload"
    uploaded = "uploaded"

    # download
    downloading = "downloading"
    failed_to_download = "failed_to_download"
    downloaded = "downloaded"

    # write
    waiting_for_card = "waiting_for_card"
    failed_to_insert = "failed_to_insert"
    card_inserted = "card_inserted"
    wiping_sdcard = "wiping_sdcard"
    failed_to_wipe = "failed_to_wipe"
    card_wiped = "card_wiped"
    writing = "writing"
    failed_to_write = "failed_to_write"
    written = "written"
    pending_image_removal = "pending_image_removal"
    downloaded_failed_to_remove = "downloaded_failed_to_remove"
    downloaded_and_removed = "downloaded_and_removed"

    failed = "failed"
    canceled = "canceled"
    timedout = "timedout"

    PENDING_STATUSES = [pending, waiting_for_card, pending_image_removal]
    WORKING_STATUSES = [
        received,
        building,
        built,
        uploading,
        downloading,
        downloaded,
        wiping_sdcard,
        card_wiped,
        writing,
    ]
    FAILED_STATUSES = [
        failed_to_build,
        failed_to_upload,
        failed_to_download,
        failed_to_insert,
        failed_to_wipe,
        failed_to_write,
        failed,
        canceled,
        timedout,
    ]

    CREATOR_SUCCESS_STATUSES = [uploaded]
    DOWNLOADER_SUCCESS_STATUSES = [
        downloaded,
        pending_image_removal,
        downloaded_and_removed,
    ]
    WRITER_SUCCESS_STATUSES = [written]
    SUCCESS_STATUSES = CREATOR_SUCCESS_STATUSES + WRITER_SUCCESS_STATUSES

    @classmethod
    def get(cls, task_id, projection=None):
        return cls().find_one({"_id": task_id}, projection)

    @classmethod
    def cascade_status(cls, task_id, task_status):
        task = cls.get(task_id)

        cascade_map = {
            Tasks.received: Orders.creating,
            Tasks.building: Orders.creating,
            Tasks.failed_to_build: Orders.creation_failed,
            Tasks.built: Orders.creating,
            Tasks.uploading: Orders.creating,
            Tasks.failed_to_upload: Orders.creation_failed,
            Tasks.uploaded: Orders.pending_writer,
            Tasks.downloading: Orders.downloading,
            Tasks.failed_to_download: Orders.download_failed,
            Tasks.downloaded: Orders.writing,
            Tasks.waiting_for_card: Orders.writing,
            Tasks.card_inserted: Orders.writing,
            Tasks.failed_to_insert: Orders.write_failed,
            Tasks.wiping_sdcard: Orders.writing,
            Tasks.card_wiped: Orders.writing,
            Tasks.failed_to_wipe: Orders.write_failed,
            Tasks.writing: Orders.writing,
            Tasks.failed_to_write: Orders.write_failed,
            Tasks.written: Orders.pending_shipment,
            Tasks.failed: Orders.failed,
            Tasks.canceled: Orders.canceled,
            Tasks.timedout: Orders.failed,
        }

        order_status = cascade_map.get(task_status)
        if not order_status:
            return

        Orders().update_status(order_id=task["order"], status=order_status)

    @classmethod
    def update_logs(
        cls,
        task_id,
        worker_log=None,
        installer_log=None,
        uploader_log=None,
        downloader_log=None,
    ):
        if worker_log is None and installer_log is None:
            return
        update = {}
        if worker_log is not None:
            update.update({"logs.worker": worker_log})
        if installer_log is not None:
            update.update({"logs.installer": installer_log})
        if uploader_log is not None:
            update.update({"logs.uploader": uploader_log})
        if downloader_log is not None:
            update.update({"logs.downloader": downloader_log})

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

    schema = {
        "order": {"type": "string", "required": True},
        "channel": {"type": "string", "required": True, "nullable": True},
        "worker": {"type": "string", "required": True, "nullable": True},
        "config": {"type": "dict", "required": True},
        "size": {"type": "integer", "required": True},
        "logs": {"type": "dict"},
        "image": {"type": "dict", "required": False},
        "status": {"type": "string", "required": True},
        "statuses": {"type": "list"},
    }

    def __init__(self):
        super().__init__(Database(), "creator_tasks")


class DownloaderTasks(Tasks):

    schema = {
        "order": {"type": "string", "required": True},
        "channel": {"type": "string", "required": True, "nullable": True},
        "worker": {"type": "string", "required": True, "nullable": True},
        "download_uri": {"type": "string", "required": True},
        "image_fname": {"type": "string", "regex": "^.+$", "required": True},
        "image_checksum": {"type": "string", "required": True},
        "image_size": {"type": "integer", "required": True},  # bytes
        "logs": {"type": "list"},
        "status": {"type": "string", "required": True},
        "statuses": {"type": "list"},
    }

    def __init__(self):
        super().__init__(Database(), "downloader_tasks")


class WriterTasks(Tasks):

    schema = {
        "order": {"type": "string", "required": True},
        "channel": {"type": "string", "required": True, "nullable": True},
        "worker": {"type": "string", "required": True, "nullable": True},
        "name": {"type": "string", "regex": "^.+$", "required": True},
        "image_checksum": {"type": "string", "required": True},
        "image_size": {"type": "integer", "required": True},  # bytes
        "sd_size": {"type": "integer", "required": True},
        "logs": {"type": "list"},
        "status": {"type": "string", "required": True},
        "statuses": {"type": "list"},
    }

    def __init__(self):
        super().__init__(Database(), "writer_tasks")
