import os
import sys

from werkzeug.security import generate_password_hash
from cerberus import Validator
from pymongo import ASCENDING

from utils import mongo


class Initializer:
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
    def create_initial_user():
        all_access = {
            "scope": {
                "users": {"read": True, "create": True, "delete": True, "update": True},
                "channels": {
                    "read": True,
                    "create": True,
                    "delete": True,
                    "update": True,
                },
                "orders": {
                    "read": True,
                    "create": True,
                    "delete": True,
                    "update": True,
                },
                "creator_tasks": {
                    "read": True,
                    "create": True,
                    "delete": True,
                    "update": True,
                },
                "writer_tasks": {
                    "read": True,
                    "create": True,
                    "delete": True,
                    "update": True,
                },
                "task": {"create": True, "delete": True},
            }
        }

        users = mongo.Users()
        if users.find_one() is not None:
            return

        for username, password, email in [
            (
                os.getenv("INIT_USERNAME", "admin"),
                os.getenv("INIT_PASSWORD", "admin_pass"),
                os.getenv("INIT_EMAIL", "reg@kiwix.org"),
            ),
            ("manager", os.getenv("MANAGER_API_KEY", "manager"), "manager@kiwix.org"),
        ]:

            document = {
                "username": username,
                "password_hash": generate_password_hash(password),
                "email": email,
            }

            document.update(all_access)
            validator = Validator(mongo.Users.schema)
            if not validator.validate(document):
                sys.exit()
            print(users.insert_one(document))


if __name__ == "__main__":
    print("Running pre-start initialization...")
    if False:  # DEBUG
        nb_removed = mongo.Users().remove({}, False)
        print("nb_removed", nb_removed)
    Initializer.create_database_indexes()
    Initializer.create_initial_user()
