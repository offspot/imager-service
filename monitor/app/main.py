import os
import sys

from celery import Celery
from pymongo import MongoClient, database


class Client(MongoClient):
    def __init__(self):
        super().__init__(host="mongo")


class Database(database.Database):
    def __init__(self):
        super().__init__(Client(), "Cardshop")


def process_event(event: dict):
    pass


if __name__ == "__main__":
    try:
        system_username = "system"
        system_password = os.getenv("SYSTEM_PASSWORD", "")
        url = "amqp://{username}:{password}@rabbit:5672/cardshop".format(
            username=system_username, password=system_password
        )
        celery = Celery(broker=url)
        with celery.connection() as connection:
            recv = celery.events.Receiver(connection, handlers={"*": process_event})
            recv.capture(limit=None, timeout=None, wakeup=True)
    except (KeyboardInterrupt, SystemExit):
        print("\n", "Interrupted", sep="")
        sys.exit()
