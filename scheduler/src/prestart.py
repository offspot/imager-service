#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import socket
import logging

from werkzeug.security import generate_password_hash
from cerberus import Validator
from pymongo import ASCENDING

from utils import mongo
from emailing import send_email

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
            logger.info("removed {} channels".format(mongo.Channels().remove({})))
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
                os.getenv("MANAGER_API_KEY", "manager")
            ),
            "email": "manager@kiwix.org",
            "role": mongo.Users.MANAGER_ROLE,
            "active": True,
            "scope": {},
        }

        validator = Validator(mongo.Users.schema)
        if not validator.validate(user_document):
            logger.info("user_document is not valid for schema")
        else:
            logger.info("created user", mongo.Users().insert_one(user_document))

        channel_document = {
            "slug": "kiwix",
            "name": "Kiwix",
            "active": True,
            "private": False,
        }

        validator = Validator(mongo.Channels.schema)
        if not validator.validate(channel_document):
            logger.info("channel_document is not valid for schema")
        else:
            logger.info(
                "created channel", mongo.Channels().insert_one(channel_document)
            )

        warehouse_document = {
            "slug": "kiwix",
            "upload_uri": os.getenv(
                "DEFAULT_WAREHOUSE_UPLOAD_URI",
                "ftp://warehouse.cardshop.hotspot.kiwix.org:2121",
            ),
            "download_uri": os.getenv(
                "DEFAULT_WAREHOUSE_DOWNLOAD_URI",
                "http://warehouse.cardshop.hotspot.kiwix.org",
            ),
            "active": True,
        }

        validator = Validator(mongo.Warehouses.schema)
        if not validator.validate(warehouse_document):
            logger.info("warehouse_document is not valid for schema")
        else:
            logger.info(
                "created warehouse", mongo.Warehouses().insert_one(warehouse_document)
            )


if __name__ == "__main__":
    Initializer.start()
