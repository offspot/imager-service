#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import re
import logging

from django import forms
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect
from django.core import validators

from manager.decorators import staff_required
from manager.scheduler import (
    test_connection,
    get_channels_list,
    get_users_list,
    get_workers_list,
    as_items_or_none,
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
    ACCESS_TOKEN,
    get_channel_choices,
    get_warehouse_choices,
    get_autoimages_list,
    add_autoimage,
    delete_autoimage,
)
from manager.models import Configuration

logger = logging.getLogger(__name__)


class SchedulerForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self._client = kwargs.pop("client")
        super().__init__(*args, **kwargs)


class ChannelForm(SchedulerForm):
    slug = forms.CharField()
    name = forms.CharField()
    active = forms.BooleanField(initial=True, required=False)
    private = forms.BooleanField(initial=False, required=False)
    sender_name = forms.CharField()
    sender_address = forms.CharField(widget=forms.Textarea)
    sender_email = forms.EmailField()

    @staticmethod
    def success_message(result):
        return "Successfuly created channel <em>{channel}</em>".format(channel=result)

    def clean_slug(self):
        if not re.match(r"^[a-zA-Z0-9_.+-]+$", self.cleaned_data.get("slug")):
            raise forms.ValidationError("Prohibited Characters", code="invalid")
        return self.cleaned_data.get("slug")

    def save(self):
        if not self.is_valid():
            raise ValueError("{cls} is not valid".format(cls=type(self)))

        success, channel_id = add_channel(
            slug=self.cleaned_data.get("slug"),
            name=self.cleaned_data.get("name"),
            active=self.cleaned_data.get("active"),
            private=self.cleaned_data.get("private"),
            sender_name=self.cleaned_data.get("sender_name"),
            sender_email=self.cleaned_data.get("sender_email"),
            sender_address=self.cleaned_data.get("sender_address"),
        )
        if not success:
            raise SchedulerAPIError(channel_id)
        return channel_id


class S3URLFormField(forms.URLField):
    default_validators = [
        validators.URLValidator(
            schemes=[
                "http",
                "https",
                "ftp",
                "ftps",
                "s3",
                "http+torrent",
                "https+torrent",
            ]
        )
    ]


class WarehouseForm(SchedulerForm):
    slug = forms.CharField()
    upload_uri = S3URLFormField()
    download_uri = S3URLFormField()
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
            raise ValueError("{cls} is not valid".format(cls=type(self)))

        success, warehouse_id = add_warehouse(
            slug=self.cleaned_data.get("slug"),
            upload_uri=self.cleaned_data.get("upload_uri"),
            download_uri=self.cleaned_data.get("download_uri"),
            active=self.cleaned_data.get("active"),
        )
        if not success:
            raise SchedulerAPIError(warehouse_id)
        return warehouse_id


class UserForm(SchedulerForm):
    username = forms.CharField()
    role = forms.ChoiceField(choices=ROLES.items())
    channel = forms.ChoiceField(choices=get_channel_choices())
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
            raise ValueError("{cls} is not valid".format(cls=type(self)))

        success, user_id = add_user(
            username=self.cleaned_data.get("username"),
            email=self.cleaned_data.get("email"),
            password=self.cleaned_data.get("password"),
            role=self.cleaned_data.get("role"),
            channel=self.cleaned_data.get("channel"),
            is_admin=self.cleaned_data.get("is_admin"),
        )

        if not success:
            raise SchedulerAPIError(user_id)

        return user_id


class ImageForm(SchedulerForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["config"].choices = Configuration.get_choices(
            self._client.organization
        )

    slug = forms.CharField(label="Image ID/slug")
    config = forms.ChoiceField(choices=[], label="Configuration")
    contact_email = forms.EmailField(label="Contact Email")
    warehouse = forms.ChoiceField(choices=get_warehouse_choices())
    channel = forms.ChoiceField(choices=get_channel_choices())
    private = forms.BooleanField(initial=True, required=True)
    active = forms.BooleanField(initial=True, required=False)

    @staticmethod
    def success_message(result):
        return f"Successfuly created Auto Image <em>{result}</em>"

    def clean_slug(self):
        if not re.match(r"^[a-zA-Z0-9_.+-]+$", self.cleaned_data.get("slug")):
            raise forms.ValidationError("Prohibited Characters", code="invalid")
        return self.cleaned_data.get("slug")

    def clean_config(self):
        config = Configuration.get_or_none(self.cleaned_data.get("config"))
        if config is None or config.organization != self._client.organization:
            raise forms.ValidationError("Not your configuration", code="invalid")
        return config

    def save(self):
        if not self.is_valid():
            raise ValueError("{cls} is not valid".format(cls=type(self)))

        success, autoimage_slug = add_autoimage(
            slug=self.cleaned_data.get("slug"),
            config=self.cleaned_data.get("config").to_dict(),
            contact_email=self.cleaned_data.get("contact_email"),
            periodicity="monthly",
            warehouse=self.cleaned_data.get("warehouse"),
            channel=self.cleaned_data.get("channel"),
            private=self.cleaned_data.get("private")
        )
        if not success:
            raise SchedulerAPIError(autoimage_slug)
        return autoimage_slug


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
        "workers": as_items_or_none(*get_workers_list()) or None,
        "images": as_items_or_none(*get_autoimages_list()) or None,
        "api_url": settings.CARDSHOP_API_URL,
    }

    forms_map = {
        "channel_form": ChannelForm,
        "user_form": UserForm,
        "warehouse_form": WarehouseForm,
        "image_form": ImageForm,
    }
    for key, value in forms_map.items():
        context[key] = value(prefix=key, client=request.user.profile)

    if request.method == "POST" and request.POST.get("form") in forms_map.keys():

        # which form is being saved?
        form_key = request.POST.get("form")
        context[form_key] = forms_map.get(form_key)(
            request.POST, prefix=form_key, client=request.user.profile
        )

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
    logger.info("Re-authenticated against the scheduler: `{}`".format(ACCESS_TOKEN))
    messages.info(
        request,
        "Re-authenticated against the scheduler: <code>{}</code>".format(
            ACCESS_TOKEN[:20]
        ),
    )
    return redirect("scheduler")


staff_required


def image_delete(request, image_slug):
    success, _ = delete_autoimage(image_slug)
    if not success:
        logger.error(f"Unable to delete image: {image_slug}")
        messages.error(request, f"Unable to delete image: -- ref: {image_slug}")
    else:
        messages.success(request, f"Successfuly deleted image: {image_slug}")

    return redirect("scheduler")
