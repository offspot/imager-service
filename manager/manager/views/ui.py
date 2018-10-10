#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging

from django import forms
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required

from manager.scheduler import (
    test_connection,
    get_channels_list,
    get_users_list,
    as_items_or_none,
    get_orders_list,
)

logger = logging.getLogger(__name__)


@login_required
def home(request):
    context = {"support_email": settings.SUPPORT_EMAIL}

    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            try:
                form.save()
            except Exception as exp:
                logger.error(exp)
                messages.error(
                    request,
                    "Failed to update your password although it looks good. (ref: {exp})".format(
                        exp=exp
                    ),
                )
            else:
                messages.success(request, "Password Updated successfuly !")
                update_session_auth_hash(request, form.user)
                return redirect("home")
    else:
        form = PasswordChangeForm(user=request.user)
    context["password_form"] = form
    return render(request, "home.html", context)


@login_required
def orders(request):
    return render(request, "home.html", {})


@login_required
def scheduler(request):
    context = {}

    success, code, _ = test_connection()
    if not success:
        messages.error(
            request,
            "Unable to connect (HTTP {code}) to API at <code>{url}</code>".format(
                url=settings.CARDSHOP_API_URL, code=code
            ),
        )
        return render(request, "scheduler.html", context)
    else:
        messages.set_level(request, messages.DEBUG)
        messages.debug(
            request,
            "Connected to Scheduler API at <code>{url}</code>".format(
                url=settings.CARDSHOP_API_URL
            ),
        )

    # channels
    context["channels"] = as_items_or_none(*get_channels_list()) or []

    # users
    context["users"] = as_items_or_none(*get_users_list()) or []

    context["orders"] = as_items_or_none(*get_orders_list()) or []

    return render(request, "scheduler.html", context)
