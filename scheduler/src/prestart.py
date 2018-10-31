import os

from werkzeug.security import generate_password_hash
from cerberus import Validator
from pymongo import ASCENDING

from utils import mongo
from emailing import send_email


class Initializer:
    @staticmethod
    def start():
        print("send test email")
        if os.getenv("TEST_EMAIL"):
            send_email(os.getenv("TEST_EMAIL"), "scheduler test", "started a scheduler")
        print("Running pre-start initialization...")
        if bool(os.getenv("RESET_DB", False)):
            print("removed {} tokens".format(mongo.RefreshTokens().remove({}, False)))
            print("removed {} users".format(mongo.Users().remove({}, False)))
            print("removed {} channels".format(mongo.Channels().remove({}, False)))
            print("removed {} orders".format(mongo.Orders().remove({}, False)))
            print(
                "removed {} creator_tasks".format(
                    mongo.CreatorTasks().remove({}, False)
                )
            )
            print(
                "removed {} writer_tasks".format(mongo.WriterTasks().remove({}, False))
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
            print("we already have users. not creating initial data")
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
            print("user_document is not valid for schema")
        else:
            print("created user", mongo.Users().insert_one(user_document))

        channel_document = {
            "slug": "kiwix",
            "name": "Kiwix",
            "active": True,
            "private": False,
        }

        validator = Validator(mongo.Channels.schema)
        if not validator.validate(channel_document):
            print("channel_document is not valid for schema")
        else:
            print("created user", mongo.Channels().insert_one(channel_document))


if __name__ == "__main__":
    Initializer.start()
