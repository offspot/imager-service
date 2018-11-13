#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import re
import logging

from django import forms
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect

from manager.decorators import staff_required
from manager.scheduler import (
    test_connection,
    get_channels_list,
    get_users_list,
    as_items_or_none,
    get_orders_list,
    add_channel,
    add_warehouse,
    get_warehouses_list,
    enable_warehouse,
    disable_warehouse,
    add_user,
    ROLES,
    SchedulerAPIError,
    enable_channel,
    disable_channel,
    enable_user,
    disable_user,
    authenticate,
    TOKEN,
)

logger = logging.getLogger(__name__)


class ChannelForm(forms.Form):
    slug = forms.CharField()
    name = forms.CharField()
    active = forms.BooleanField(initial=True, required=False)
    private = forms.BooleanField(initial=False, required=False)

    @staticmethod
    def success_message(result):
        return "Successfuly created channel <em>{channel}</em>".format(channel=result)

    def clean_slug(self):
        if not re.match(r"^[a-zA-Z0-9_.+-]+$", self.cleaned_data.get("slug")):
            raise forms.ValidationError("Prohibited Characters", code="invalid")
        return self.cleaned_data.get("slug")

    def save(self):
        if not self.is_valid():
            raise ValueError("{cls} is not valid".format(type(self)))

        success, channel_id = add_channel(
            slug=self.cleaned_data.get("slug"),
            name=self.cleaned_data.get("name"),
            active=self.cleaned_data.get("active"),
            private=self.cleaned_data.get("private"),
        )
        if not success:
            raise SchedulerAPIError(channel_id)
        return channel_id


class WarehouseForm(forms.Form):
    slug = forms.CharField()
    upload_uri = forms.URLField()
    download_uri = forms.URLField()
    active = forms.BooleanField(initial=True, required=False)

    @staticmethod
    def success_message(result):
        return "Successfuly created warehouse <em>{warehouse}</em>".format(
            warehouse=result
        )

    def clean_slug(self):
        if not re.match(r"^[a-zA-Z0-9_.+-]+$", self.cleaned_data.get("slug")):
            raise forms.ValidationError("Prohibited Characters", code="invalid")
        return self.cleaned_data.get("slug")

    def save(self):
        if not self.is_valid():
            raise ValueError("{cls} is not valid".format(type(self)))

        success, warehouse_id = add_warehouse(
            slug=self.cleaned_data.get("slug"),
            upload_uri=self.cleaned_data.get("upload_uri"),
            download_uri=self.cleaned_data.get("download_uri"),
            active=self.cleaned_data.get("active"),
        )
        if not success:
            raise SchedulerAPIError(warehouse_id)
        return warehouse_id


class UserForm(forms.Form):
    username = forms.CharField()
    role = forms.ChoiceField(choices=ROLES.items())
    email = forms.EmailField()
    password = forms.CharField()

    @staticmethod
    def success_message(result):
        return "Successfuly created User <em>{user}</em>".format(user=result)

    def clean_username(self):
        if not re.match(r"^[a-zA-Z0-9_.+-]+$", self.cleaned_data.get("username")):
            raise forms.ValidationError("Prohibited Characters", code="invalid")
        return self.cleaned_data.get("username")

    def clean_email(self):
        if not re.match(
            r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
            self.cleaned_data.get("email"),
        ):
            raise forms.ValidationError("Invalid format", code="invalid")
        return self.cleaned_data.get("email")

    def save(self):
        if not self.is_valid():
            raise ValueError("{cls} is not valid".format(type(self)))

        success, user_id = add_user(
            username=self.cleaned_data.get("username"),
            email=self.cleaned_data.get("email"),
            password=self.cleaned_data.get("password"),
            role=self.cleaned_data.get("role"),
            is_admin=self.cleaned_data.get("is_admin"),
        )

        if not success:
            raise SchedulerAPIError(user_id)

        return user_id


@staff_required
def dashboard(request):

    success, code, msg = test_connection()
    if not success:
        messages.error(
            request,
            "Unable to connect (HTTP {code}) to API at <code>{url}</code>{msg}".format(
                url=settings.CARDSHOP_API_URL,
                code=code,
                msg=" -- " + msg if msg else "",
            ),
        )
        return redirect("admin")

    context = {
        "channels": as_items_or_none(*get_channels_list()) or None,
        "warehouses": as_items_or_none(*get_warehouses_list()) or None,
        "users": as_items_or_none(*get_users_list()) or None,
    }

    forms_map = {
        "channel_form": ChannelForm,
        "user_form": UserForm,
        "warehouse_form": WarehouseForm,
    }
    for key, value in forms_map.items():
        context[key] = value(prefix=key)

    if request.method == "POST" and request.POST.get("form") in forms_map.keys():

        # which form is being saved?
        form_key = request.POST.get("form")
        context[form_key] = forms_map.get(form_key)(request.POST, prefix=form_key)

        if context[form_key].is_valid():
            try:
                res = context[form_key].save()
            except Exception as exp:
                logger.error(exp)
                messages.error(request, "Error while saving… {exp}".format(exp=exp))
            else:
                messages.success(request, context[form_key].success_message(res))
                return redirect("scheduler")

    if success:
        messages.set_level(request, messages.DEBUG)
        messages.debug(
            request,
            "Connected to Scheduler API at <code>{url}</code>".format(
                url=settings.CARDSHOP_API_URL
            ),
        )

    return render(request, "scheduler.html", context)


@staff_required
def channel_enable(request, channel_id):
    success, channel_id = enable_channel(channel_id)
    if not success:
        logger.error("Unable to enable channel: {}".format(channel_id))
        messages.error(
            request, "Unable to enable Channel: -- ref: {}".format(channel_id)
        )
    else:
        messages.success(request, "Successfuly enabled channel: {}".format(channel_id))

    return redirect("scheduler")


@staff_required
def channel_disable(request, channel_id):
    success, channel_id = disable_channel(channel_id)
    if not success:
        logger.error("Unable to disable channel: {}".format(channel_id))
        messages.error(
            request, "Unable to disable Channel: -- ref: {}".format(channel_id)
        )
    else:
        messages.success(request, "Successfuly disabled channel: {}".format(channel_id))

    return redirect("scheduler")


@staff_required
def warehouse_enable(request, warehouse_id):
    success, warehouse_id = enable_warehouse(warehouse_id)
    if not success:
        logger.error("Unable to enable warehouse: {}".format(warehouse_id))
        messages.error(
            request, "Unable to enable Channel: -- ref: {}".format(warehouse_id)
        )
    else:
        messages.success(
            request, "Successfuly enabled warehouse: {}".format(warehouse_id)
        )

    return redirect("scheduler")


@staff_required
def warehouse_disable(request, warehouse_id):
    success, warehouse_id = disable_warehouse(warehouse_id)
    if not success:
        logger.error("Unable to disable warehouse: {}".format(warehouse_id))
        messages.error(
            request, "Unable to disable Channel: -- ref: {}".format(warehouse_id)
        )
    else:
        messages.success(
            request, "Successfuly disabled warehouse: {}".format(warehouse_id)
        )

    return redirect("scheduler")


@staff_required
def user_enable(request, user_id):
    success, user_id = enable_user(user_id)
    if not success:
        logger.error("Unable to enable user: {}".format(user_id))
        messages.error(request, "Unable to enable user: -- ref: {}".format(user_id))
    else:
        messages.success(request, "Successfuly enabled user: {}".format(user_id))

    return redirect("scheduler")


@staff_required
def user_disable(request, user_id):
    success, user_id = disable_user(user_id)
    if not success:
        logger.error("Unable to disable user: {}".format(user_id))
        messages.error(request, "Unable to disable user: -- ref: {}".format(user_id))
    else:
        messages.success(request, "Successfuly disabled user: {}".format(user_id))

    return redirect("scheduler")


@staff_required
def refresh_token(request):
    authenticate(force=True)
    logger.info("Re-authenticated against the scheduler: `{}`".format(TOKEN))
    messages.info(
        request,
        "Re-authenticated against the scheduler: <code>{}</code>".format(TOKEN[:20]),
    )
    return redirect("scheduler")
