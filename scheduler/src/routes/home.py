#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from flask import Blueprint, request, jsonify

from utils.mongo import Users
from . import (
    authenticate,
    ensure_user_matches_role,
)


blueprint = Blueprint("home", __name__, url_prefix="")


@blueprint.route("/", methods=["GET"])
@authenticate()
def collection(user: dict):
    """ ensure a user can auth and access the API """

    if request.method == "GET":
        # check user permission
        ensure_user_matches_role(user, Users.ROLES)

        return jsonify({"message": "Hello World"})
