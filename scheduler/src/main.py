#!/usr/bin/env python

import logging
import os

from babel.dates import format_datetime
from flask import Flask
from flask_cors import CORS
from prestart import Initializer
from routes import (
    auth,
    autoimages,
    channels,
    errors,
    home,
    orders,
    tasks,
    users,
    warehouses,
    workers,
    woo,
)
from utils.json import Encoder
from utils.templates import amount_str, strftime, country_name


def format_dt(date, fmt="d MMMM yyyy, HH:mm", locale="en_GB"):
    """format datetime using babel. Format optional"""
    return format_datetime(date, fmt, locale=locale)


logging.basicConfig(level=logging.INFO)

flask = Flask(__name__)
flask.json_encoder = Encoder
flask.jinja_env.filters["amount"] = amount_str
flask.jinja_env.filters["date"] = format_dt
flask.jinja_env.filters["country"] = country_name
CORS(flask)

flask.register_blueprint(home.blueprint)
flask.register_blueprint(auth.blueprint)
flask.register_blueprint(users.blueprint)
flask.register_blueprint(channels.blueprint)
flask.register_blueprint(orders.blueprint)
flask.register_blueprint(tasks.blueprint)
flask.register_blueprint(warehouses.blueprint)
flask.register_blueprint(workers.blueprint)
flask.register_blueprint(autoimages.blueprint)
flask.register_blueprint(woo.blueprint)

errors.register_handlers(flask)


if __name__ == "__main__":
    Initializer.start()

    is_debug = os.getenv("DEBUG", False)
    flask.run(
        host="0.0.0.0",
        debug=is_debug,
        port=int(os.getenv("PORT", "80")),
        threaded=True,
    )
