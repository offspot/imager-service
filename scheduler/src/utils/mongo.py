import datetime
import os

import humanfriendly
from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection as BaseCollection
from pymongo.database import Database as BaseDatabase

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
            "regex": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        },
        "password_hash": {"type": "string", "required": True},
        "active": {"type": "boolean", "default": True, "required": True},
        "channel": {"type": "string", "required": True},
        "role": {"type": "string", "required": True},
    }

    def __init__(self):
        super().__init__(Database(), "users")

    @classmethod
    def by_username(cls, username):
        return cls().find_one({"username": username})

    @classmethod
    def get_manager(cls):
        return cls().find_one({"role": cls.MANAGER_ROLE})


class RefreshTokens(BaseCollection):
    def __init__(self):
        super().__init__(Database(), "refresh_tokens")


class Acknowlegments(BaseCollection):

    idle = "idle"
    busy = "busy"
    not_starting = "not_starting"
    error = "error"
    no_slot = "no_slot"

    def __init__(self):
        super().__init__(Database(), "acknowlegments")

    schema = {
        "username": {"type": "string", "regex": "^[a-zA-Z0-9_.+-]+$", "required": True},
        "worker_type": {"type": "string", "required": True},
        "slot": {"type": "string", "required": True},
        "status": {"type": "string", "required": True},
        "on": {"type": "datetime", "required": True},
        "payload": {"type": "string", "required": False},
    }

    @classmethod
    def update(
        cls, username, worker_type, slot, status, payload=None, extra={}, on=None
    ):
        # retrieve previsous status
        mfilter = {"username": username, "worker_type": worker_type, "slot": slot}
        existing = cls().find_one(mfilter, {"status"})
        previous_status = existing["status"] if existing else None
        # update ack
        extra.update(
            {"status": status, "on": datetime.datetime.now(), "payload": payload}
        )
        res = cls().update_one(mfilter, {"$set": extra}, upsert=True)
        return res.upserted_id or existing["_id"], status != previous_status

    @classmethod
    def idle_update(cls, username, worker_type, slot):
        return cls.update(
            username=username, worker_type=worker_type, slot=slot, status=cls.idle
        )

    @classmethod
    def busy_update(cls, username, worker_type, slot, task_id):
        return cls.update(
            username=username,
            worker_type=worker_type,
            slot=slot,
            status=cls.busy,
            payload="task #{}".format(task_id),
        )

    @classmethod
    def sos_update(cls, username, worker_type, slot, error):
        return cls.update(
            username=username,
            worker_type=worker_type,
            slot=slot,
            status=cls.not_starting,
            payload=error,
        )

    @classmethod
    def get(cls, aid):
        ack = cls().find_one({"_id": aid})
        if ack is None:
            raise ValueError("Unable to retrieve ack with id `{}`".format(aid))
        return ack


class Channels(BaseCollection):
    schema = {
        "slug": {"type": "string", "regex": "^[a-zA-Z0-9_.+-]+$", "required": True},
        "name": {"type": "string", "regex": "^.+$", "required": True},
        "active": {"type": "boolean", "default": True, "required": True},
        "private": {"type": "boolean", "default": False, "required": True},
        "sender_name": {"type": "string", "regex": "^.+$", "required": True},
        "sender_address": {"type": "string", "required": True},
        "sender_email": {
            "type": "string",
            "regex": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        },
    }

    def __init__(self):
        super().__init__(Database(), "channels")

    @classmethod
    def get(cls, slug):
        channel = cls().find_one({"slug": slug})
        if channel is None:
            raise ValueError("Unable to retrieve channel with slug `{}`".format(slug))
        return channel


class Warehouses(BaseCollection):
    schema = {
        "slug": {"type": "string", "regex": "^[a-zA-Z0-9_.+-]+$", "required": True},
        "upload_uri": {"type": "string", "regex": "^.+$", "required": True},
        "download_uri": {"type": "string", "regex": "^.+$", "required": True},
        "active": {"type": "boolean", "default": True, "required": True},
    }

    def __init__(self):
        super().__init__(Database(), "warehouses")

    @classmethod
    def get(cls, slug):
        order = cls().find_one({"slug": slug})
        if order is None:
            raise ValueError(f"Unable to find/retrieve object with slug {slug}")
        return order


class Orders(BaseCollection):

    virtual = "virtual"
    physical = "physical"

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
    pending_expiry = "pending_expiry"
    expired = "expired"
    canceled = "canceled"
    failed = "failed"

    PENDING_STATUSES = [
        created,
        pending_creator,
        pending_writer,
        pending_shipment,
        pending_expiry,
    ]
    WORKING_STATUSES = [creating, downloading, writing]
    FAILED_STATUSES = [creation_failed, download_failed, write_failed, canceled, failed]
    SUCCESS_STATUSES = [shipped, expired]

    schema = {
        "config": {"type": "dict", "required": True},
        "config_yaml": {"type": "string", "required": False},
        "sd_card": {
            "type": "dict",
            "required": True,
            "schema": {
                "name": {"type": "string", "required": True},
                "type": {"type": "string", "required": True},
                "size": {"type": "integer", "required": True},
                "expiration": {"type": "datetime", "required": False},
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
                    "regex": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
                    "required": True,
                },
                "limited": {"type": "boolean", "required": False},
                "language": {
                    "type": "string",
                    "regex": "^[a-zA-Z]{2}$",
                    "required": False,
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
                    "regex": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
                    "required": False,
                },
                "phone": {"type": "string", "regex": r"^\+?[0-9]+$", "required": False},
                "address": {"type": "string", "required": True},
                "country": {"type": "string", "required": True},
                "shipment": {"type": "string", "required": False, "nullable": True},
                "language": {
                    "type": "string",
                    "regex": "^[a-zA-Z]{2}$",
                    "required": False,
                },
            },
        },
        "warehouse": {"type": "dict", "required": False},
        "channel": {"type": "string", "required": True},
        "statuses": {"type": "list", "required": False},
        "logs": {"type": "list", "required": False},
        "tasks": {"type": "dict", "required": False},
    }

    def __init__(self):
        super().__init__(Database(), "orders")

    @classmethod
    def get(cls, order_id, with_logs=False):
        order = cls().find_one(
            {"_id": ensure_objectid(order_id)},
            projection={"logs": 0} if not with_logs else None,
        )
        if order is None:
            raise ValueError(
                "Unable to find/retrieve object with ID {}".format(order_id)
            )
        return order

    @classmethod
    def get_tasks(cls, order_id, with_logs=False):
        order = cls().get(order_id)
        return {
            "create": CreatorTasks().get(
                order["tasks"].get("create"), with_logs=with_logs
            ),
            "download": DownloaderTasks().get(
                order["tasks"].get("download"), with_logs=with_logs
            ),
            "write": [
                WriterTasks().get(task, with_logs=with_logs)
                for task in order["tasks"].get("write", [])
            ],
        }

    @classmethod
    def get_with_tasks(cls, order_id, with_logs=False):
        try:
            order = cls().get(order_id, with_logs=with_logs)
        except ValueError:
            order = None
        if order is None:
            return order
        order["tasks"].update(cls().get_tasks(order_id, with_logs=with_logs))
        return order

    @classmethod
    def update(cls, order_id, update_set):
        cls().update_one({"_id": ObjectId(order_id)}, {"$set": update_set})

    @classmethod
    def create_creator_task(cls, order_id):
        order = cls.get(order_id)
        if order is None:
            raise ValueError("Order #{} not exists. can't create task".format(order_id))

        payload = {
            "order": order_id,
            "media_type": order["sd_card"]["type"],
            "media_duration": order["sd_card"]["duration"],
            "channel": order["channel"],
            "fname": order["fname"],
            "upload_uri": order["warehouse"]["upload_uri"],
            "download_uri": order["warehouse"]["download_uri"],
            "worker": None,
            "config": order["config"],
            "config_yaml": order.get("config_yaml", ""),
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
    def cancel(cls, order_id):
        cls.update_status(order_id, cls.canceled)
        order = cls.get(order_id)
        if order["tasks"].get("create"):
            CreatorTasks().cancel(order["tasks"].get("create"))
        if order["tasks"].get("download"):
            DownloaderTasks().cancel(order["tasks"].get("download"))
        if order["tasks"].get("write"):
            for tid in order["tasks"].get("write"):
                WriterTasks().cancel(tid)

    @classmethod
    def create_downloader_task(cls, order_id, upload_details):
        order = cls.get(order_id)
        if order is None:
            raise ValueError("Order #{} not exists. can't create task".format(order_id))

        payload = {
            "order": order_id,
            "channel": order["channel"],
            "fname": order["fname"],
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
            "fname": order["fname"],
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
        for _ in range(0, order["quantity"]):
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

    @classmethod
    def add_shipment(cls, order_id, shipment_details):
        update = {"recipient.shipment": shipment_details}
        cls().update_one({"_id": ObjectId(order_id)}, {"$set": update})
        cls().update_status(order_id, Orders.shipped)

    @classmethod
    def all_pending_expiry(cls):
        return [
            cls().get(res["_id"])
            for res in cls().find({"status": cls.pending_expiry}, {"_id": 1})
        ]

    @classmethod
    def anonymize(cls, order_ids):
        order_ids = [ensure_objectid(oid) for oid in order_ids]
        query = {"_id": {"$in": order_ids}}
        if Orders().count_documents(query) != len(order_ids):
            raise ValueError("Order IDs contains incorrect one(s).")
        placeholder = "[ANONYMIZED]"
        Orders().update_many(
            query,
            {
                "$set": {
                    key: placeholder
                    for key in [
                        "client.name",
                        "client.email",
                        "recipient.name",
                        "recipient.email",
                        "recipient.phone",
                        "recipient.address",
                    ]
                }
            },
        )


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
    uploaded_public = "uploaded_public"

    # download
    downloading = "downloading"
    failed_to_download = "failed_to_download"
    downloaded = "downloaded"
    pending_end_of_writes = "pending_end_of_writes"
    pending_image_removal = "pending_image_removal"
    downloaded_failed_to_remove = "downloaded_failed_to_remove"
    downloaded_and_removed = "downloaded_and_removed"
    expired = "expired"

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

    pending_shipment = "pending_shipment"
    failed_to_ship = "failed_to_ship"
    shiped = "shiped"

    failed = "failed"
    canceled = "canceled"
    timedout = "timedout"

    PENDING_STATUSES = [
        pending,
        waiting_for_card,
        pending_image_removal,
        pending_end_of_writes,
    ]
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
    IN_PROGRESS_STATUSES = [building, uploading, downloading, wiping_sdcard, writing]

    CREATOR_SUCCESS_STATUSES = [uploaded, uploaded_public]
    DOWNLOADER_SUCCESS_STATUSES = [
        downloaded,
        pending_image_removal,
        downloaded_and_removed,
        expired,
    ]
    WRITER_SUCCESS_STATUSES = [written]
    SUCCESS_STATUSES = CREATOR_SUCCESS_STATUSES + WRITER_SUCCESS_STATUSES

    @classmethod
    def get(cls, task_id, with_logs=False):
        return cls().find_one(
            {"_id": ensure_objectid(task_id)},
            projection={"logs": 0} if not with_logs else None,
        )

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
            Tasks.uploaded_public: Orders.pending_expiry,
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
            # Tasks.written: Orders.pending_shipment,
            # Tasks.pending_end_of_writes: Orders.writing,
            # Tasks.pending_image_removal: Orders.written,
            # Tasks.downloaded_and_removed: Orders.written,
            Tasks.downloaded_failed_to_remove: Orders.written,
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
        wipe_log=None,
        writer_log=None,
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
        if wipe_log is not None:
            update.update({"logs.wipe": wipe_log})
        if writer_log is not None:
            update.update({"logs.writer": writer_log})

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
            extra_update={"worker": worker["username"]},
            payload="assigned worker: {}".format(worker["username"]),
        )

    @classmethod
    def find_availables(cls, channel):
        tasks = [
            cls.get(task.get("_id"))
            for task in cls().find({"status": cls.pending}, {"_id": 1})
        ]
        return tasks

    @classmethod
    def all_inprogress(cls):
        tasks = []
        for tcls in (CreatorTasks, DownloaderTasks, WriterTasks):
            xtasks = tcls().find(
                {"status": {"$in": cls.IN_PROGRESS_STATUSES}}, {"_id": 1}
            )
            tasks += [(tcls, tcls.get(t["_id"])) for t in xtasks]
        return tasks

    @classmethod
    def cancel(cls, task_id):
        cls.update_status(task_id, cls.canceled)

    @classmethod
    def get_size(cls, task_id):
        task = cls.get(task_id)
        if isinstance(task, CreatorTasks):
            return humanfriendly.parse_size(task["config"]["size"])
        if isinstance(task, (DownloaderTasks, WriterTasks)):
            return task["image_size"]


class CreatorTasks(Tasks):

    schema = {
        "order": {"type": "string", "required": True},
        "media_type": {"type": "string", "required": True},
        "media_duration": {"type": "string", "required": True},
        "channel": {"type": "string", "required": True, "nullable": True},
        "worker": {"type": "string", "required": True, "nullable": True},
        "config": {"type": "dict", "required": True},
        "config_yaml": {"type": "string", "required": False},
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


class AutoImages(BaseCollection):
    schema = {
        "slug": {"type": "string", "regex": "^[a-zA-Z0-9_.+-]+$", "required": True},
        "private": {"type": "boolean", "default": True, "required": True},
        "config": {"type": "dict", "required": True},
        "config_yaml": {"type": "string", "required": True},
        "contact_email": {
            "type": "string",
            "regex": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
            "required": True,
        },
        "periodicity": {"type": "string", "regex": "^.+$", "required": True},
        "warehouse": {"type": "dict", "required": False},
        "channel": {"type": "string", "required": True},
        "status": {"type": "string", "required": True, "nullable": True},
        "http_url": {"type": "string", "required": True, "nullable": True},
        "torrent_url": {"type": "string", "required": True, "nullable": True},
        "magnet_url": {"type": "string", "required": True, "nullable": True},
        "expire_on": {"type": "datetime", "required": True, "nullable": True},
        "order": {"type": "string", "required": True, "nullable": True},
    }

    update_schema = {
        "slug": {"type": "string", "regex": "^[a-zA-Z0-9_.+-]+$", "required": True},
        "private": {"type": "boolean", "default": True, "required": True},
        "config": {"type": "dict", "required": True},
        "config_yaml": {"type": "string", "required": True},
        "contact_email": {
            "type": "string",
            "regex": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
            "required": True,
        },
        "periodicity": {"type": "string", "regex": "^.+$", "required": True},
        "warehouse": {"type": "dict", "required": False},
        "channel": {"type": "string", "required": True},
    }

    def __init__(self):
        super().__init__(Database(), "autoimages")

    @classmethod
    def get(cls, slug):
        image = cls().find_one({"slug": slug})
        if image is None:
            raise ValueError("Unable to retrieve image with slug `{}`".format(slug))
        return image

    @classmethod
    def all_needing_rebuild(cls):
        return cls().find(
            {
                "$or": [
                    {"status": {"$in": [None, "failed"]}},
                    {
                        "status": "ready",
                        "expire_on": {"$lte": datetime.datetime.now()},
                    },
                ],
            }
        )

    @classmethod
    def all_currently_building(cls):
        return cls().find({"status": "building"})

    @classmethod
    def update_status(cls, slug, **update):
        cls().update_one({"slug": slug}, {"$set": update})

    @classmethod
    def create_order_payload(cls, slug):
        image = cls.get(slug)
        warehouse = Warehouses.get(image["warehouse"])
        fname = "{slug}_{period}_{rand}.img".format(
            slug=slug, period=datetime.date.today().strftime("%Y-%m"), rand="{rand}"
        )
        return {
            "config": image["config"],
            "config_yaml": image["config_yaml"],
            "fname": fname,
            "sd_card": {
                "name": "auto",
                "size": image["config"]["size"],
                "type": "virtual",
                "duration": 40,
            },
            "quantity": 1,
            "units": 0,
            "client": {
                "name": image["contact_email"],
                "email": image["contact_email"],
                "limited": False,
                "language": "en",
            },
            "recipient": {
                "name": image["contact_email"],
                "email": image["contact_email"],
                "language": "en",
                "phone": "",
                "address": "",
                "country": "",
                "shipment": None,
            },
            "channel": image["channel"],
            "warehouse": {
                "upload_uri": warehouse["upload_uri"],
                "download_uri": warehouse["download_uri"],
            },
        }


class StripeCustomer(BaseCollection):
    schema = {
        "email": {
            "type": "string",
            "regex": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
            "required": True,
        },
        "customer_id": {"type": "string", "required": True},
        "session_id": {"type": "string", "required": True},
        "product": {"type": "string", "required": True},
        "username": {"type": "string", "required": False},
    }

    def __init__(self):
        super().__init__(Database(), "stripe_customer")

    @classmethod
    def create(cls, email, customer_id):
        return (
            cls().insert_one({"email": email, "customer_id": customer_id}).inserted_id
        )

    @classmethod
    def get_or_none(cls, email):
        record = cls().find_one({"email": email}, {"customer_id": 1})
        return None if not record else record.get("customer_id")


class StripeSession(BaseCollection):
    schema = {
        "session_id": {"type": "string", "required": True},
        "customer_id": {"type": "string", "required": True},
        "product": {"type": "string", "required": True},
        "receipt_sent": {"type": "boolean", "required": True},
        "email_id": {"type": "string", "required": False},
        "username": {"type": "string", "required": False},
        "password": {"type": "string", "required": False},
        "existing_account": {"type": "boolean", "required": False},
        "expiry": {"type": "datetime", "required": False},
        "recurring": {"type": "boolean", "required": False},
        "http_url": {"type": "string", "required": False},
    }

    def __init__(self):
        super().__init__(Database(), "stripe_session")

    @classmethod
    def create(
        cls,
        customer_id,
        session_id,
        product,
        receipt_sent=False,
        **extra,
    ):
        payload = {
            "session_id": session_id,
            "customer_id": customer_id,
            "product": product,
            "receipt_sent": receipt_sent,
        }
        if extra:
            payload.update(extra)
        return cls().insert_one(payload).inserted_id

    @classmethod
    def get_or_none(cls, session_id):
        return cls().find_one({"session_id": session_id})

    @classmethod
    def get_or_none_from_inv(cls, invoice_num):
        return cls().find_one({"invoice_num": invoice_num})

    @classmethod
    def get_or_create(cls, customer_id, session_id, product, **extra):
        record = cls.get_or_none(session_id)
        if record and extra:
            cls.update(record_id=record["_id"], **extra)
        elif record:
            return record
        else:
            cls.create(
                customer_id=customer_id, session_id=session_id, product=product, **extra
            )
        return cls.get_or_none(session_id)

    @classmethod
    def update(cls, record_id, **update):
        cls().update_one({"_id": record_id}, {"$set": update})
