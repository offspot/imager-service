from pymongo import MongoClient
from pymongo.database import Database as BaseDatabase
from pymongo.collection import Collection as BaseCollection


class Client(MongoClient):
    def __init__(self):
        super().__init__(host="mongo")


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
                }
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
    }

    def __init__(self):
        super().__init__(Database(), "orders")


class CreatorTasks(BaseCollection):

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
        "worker": {"type": "string", "required": True, "nullable": True},
        "config": {"type": "dict", "required": True},
        "size": {"type": "integer", "required": True},
        "logs": {"type": "list"},
        "statuses": {"type": "list"},
    }

    def __init__(self):
        super().__init__(Database(), "creator_tasks")


class WriterTasks(BaseCollection):

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
        "worker": {"type": "string", "required": True, "nullable": True},
        "name": {"type": "string", "regex": "^.+$", "required": True},
        "image_url": {"type": "string", "required": True},
        "image_checksum": {"type": "string", "required": True},
        "image_size": {"type": "integer", "required": True},  # bytes
        "sd_size": {"type": "integer", "required": True},
        "logs": {"type": "list"},
        "statuses": {"type": "list"},
    }

    def __init__(self):
        super().__init__(Database(), "writer_tasks")
