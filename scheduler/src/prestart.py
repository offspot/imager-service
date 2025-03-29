#!/usr/bin/env python

import logging
import os
import socket

from cerberus import Validator
from emailing import send_email
from pymongo import ASCENDING
from utils import mongo
from werkzeug.security import generate_password_hash

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Initializer:
    @staticmethod
    def start():
        if os.getenv("TEST_EMAIL"):
            logger.info("send test email to: {}".format(os.getenv("TEST_EMAIL")))
            send_email(
                os.getenv("TEST_EMAIL"),
                "scheduler test",
                "started a scheduler at {}".format(socket.gethostname()),
            )
        logger.info("Running pre-start initialization...")
        if bool(os.getenv("RESET_DB", False)):
            logger.info("removed {} tokens".format(mongo.RefreshTokens().remove({})))
            logger.info("removed {} users".format(mongo.Users().remove({})))
            logger.info("removed {} ack".format(mongo.Acknowlegments().remove({})))
            logger.info("removed {} channels".format(mongo.Channels().remove({})))
            logger.info("removed {} warehouses".format(mongo.Warehouses().remove({})))
            logger.info("removed {} orders".format(mongo.Orders().remove({})))
            logger.info(
                "removed {} creator_tasks".format(mongo.CreatorTasks().remove({}))
            )
            logger.info(
                "removed {} writer_tasks".format(mongo.WriterTasks().remove({}))
            )
        Initializer.create_database_indexes()
        Initializer.create_initial_data()

    @staticmethod
    def create_database_indexes():
        mongo.Users().create_index(
            [(mongo.Users.username, ASCENDING)], name="username", unique=True
        )
        mongo.Users().create_index(
            [(mongo.Users.email, ASCENDING)], name="email", unique=True
        )
        mongo.RefreshTokens().create_index(
            [("token", ASCENDING)], name="token", unique=True
        )

    @staticmethod
    def create_initial_data():
        if mongo.Users().find_one() is not None:
            logger.info("we already have users. not creating initial data")
            return

        user_document = {
            "username": "manager",
            "password_hash": generate_password_hash(
                os.getenv("MANAGER_ACCOUNT_PASSWORD", "manager")
            ),
            "email": "manager@kiwix.org",
            "role": mongo.Users.MANAGER_ROLE,
            "channel": "kiwix",
            "active": True,
        }

        validator = Validator(mongo.Users.schema)
        if not validator.validate(user_document):
            logger.info("user_document is not valid for schema")
        else:
            logger.info(
                "created user: {}".format(mongo.Users().insert_one(user_document))
            )

        channel_document = {
            "slug": "kiwix",
            "name": "Kiwix",
            "active": True,
            "private": False,
            "sender_name": "Imager Service",
            "sender_email": "imager@kiwix.org",
            "sender_address": "c/o Studio Banana\nAvenue des acacias 7\n1 006 Lausanne, Switzerland",
        }

        validator = Validator(mongo.Channels.schema)
        if not validator.validate(channel_document):
            logger.info("channel_document is not valid for schema")
        else:
            logger.info(
                "created channel: {}".format(
                    mongo.Channels().insert_one(channel_document)
                )
            )

        warehouse_document = {
            "slug": "kiwix",
            "upload_uri": os.getenv(
                "DEFAULT_WAREHOUSE_UPLOAD_URI",
                "ftp://warehouse.cardshop.hotspot.kiwix.org:2121",
            ),
            "download_uri": os.getenv(
                "DEFAULT_WAREHOUSE_DOWNLOAD_URI",
                "ftp://warehouse.cardshop.hotspot.kiwix.org:2121",
            ),
            "active": True,
        }

        validator = Validator(mongo.Warehouses.schema)
        if not validator.validate(warehouse_document):
            logger.info("warehouse_document is not valid for schema")
        else:
            logger.info(
                "created warehouse: {}".format(
                    mongo.Warehouses().insert_one(warehouse_document)
                )
            )

        warehouse_document = {
            "slug": "download",
            "upload_uri": os.getenv(
                "DOWNLOAD_WAREHOUSE_UPLOAD_URI",
                "ftp://download.cardshop.hotspot.kiwix.org:2221",
            ),
            "download_uri": os.getenv(
                "DOWNLOAD_WAREHOUSE_DOWNLOAD_URI",
                "https://download.cardshop.hotspot.kiwix.org",
            ),
            "active": True,
        }

        validator = Validator(mongo.Warehouses.schema)
        if not validator.validate(warehouse_document):
            logger.info("warehouse_document is not valid for schema")
        else:
            logger.info(
                "created warehouse: {}".format(
                    mongo.Warehouses().insert_one(warehouse_document)
                )
            )


if __name__ == "__main__":
    Initializer.start()
