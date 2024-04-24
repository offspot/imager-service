#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 nu

import logging
import re

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core import validators
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from manager.decorators import staff_required
from manager.models import Configuration
from manager.scheduler import (
    ACCESS_TOKEN,
    ROLES,
    SchedulerAPIError,
    add_autoimage,
    add_channel,
    add_user,
    add_warehouse,
    as_items_or_none,
    authenticate,
    delete_autoimage,
    disable_channel,
    disable_user,
    disable_warehouse,
    enable_channel,
    enable_user,
    enable_warehouse,
    get_autoimages_list,
    get_channel_choices,
    get_channels_list,
    get_users_list,
    get_warehouse_choices,
    get_warehouses_list,
    get_workers_list,
    test_connection,
    update_autoimage,
)

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

    def success_message(self, result):
        return _("Successfuly created channel <em>%(channel)s</em>") % {
            "channel": result
        }

    def clean_slug(self):
        if not re.match(r"^[a-zA-Z0-9_.+-]+$", self.cleaned_data.get("slug")):
            raise forms.ValidationError(_("Prohibited Characters"), code="invalid")
        return self.cleaned_data.get("slug")

    def save(self):
        if not self.is_valid():
            raise ValueError(_("%(class)s is not valid") % {"class": type(self)})

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
    default_validators = [  # noqa: RUF012
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

    def success_message(self, result):
        return _("Successfuly created warehouse <em>%(warehouse)s</em>") % {
            "warehouse": result
        }

    def clean_slug(self):
        if not re.match(r"^[a-zA-Z0-9_.+-]+$", self.cleaned_data.get("slug")):
            raise forms.ValidationError(_("Prohibited Characters"), code="invalid")
        return self.cleaned_data.get("slug")

    def save(self):
        if not self.is_valid():
            raise ValueError(_("%(class)s is not valid") % {"class": type(self)})

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

    def success_message(self, result):
        return _("Successfuly created User <em>%(user)s</em>") % {"user": result}

    def clean_username(self):
        if not re.match(r"^[a-zA-Z0-9_.+-]+$", self.cleaned_data.get("username")):
            raise forms.ValidationError(_("Prohibited Characters"), code="invalid")
        return self.cleaned_data.get("username")

    def clean_email(self):
        if not re.match(
            r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
            self.cleaned_data.get("email"),
        ):
            raise forms.ValidationError(_("Invalid format"), code="invalid")
        return self.cleaned_data.get("email")

    def save(self):
        if not self.is_valid():
            raise ValueError(_("%(class)s is not valid") % {"class": type(self)})

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
    private = forms.BooleanField(initial=False, required=False)
    active = forms.BooleanField(initial=True, required=False)
    is_update = False

    def success_message(self, result):
        if self.is_update:
            return _(
                "Successfuly requested Update for Auto Image <em>%(img)s</em>. "
                "Will be processed shortly"
            ) % {"img": result}
        return _("Successfuly created Auto Image <em>%(img)s</em>") % {"img": result}

    def clean_slug(self):
        if not re.match(r"^[a-zA-Z0-9_.+-]+$", self.cleaned_data.get("slug")):
            raise forms.ValidationError(_("Prohibited Characters"), code="invalid")
        return self.cleaned_data.get("slug")

    def clean_config(self):
        config = Configuration.get_or_none(self.cleaned_data.get("config"))
        if config is None or config.organization != self._client.organization:
            raise forms.ValidationError(_("Not your configuration"), code="invalid")
        return config

    def save(self):
        if not self.is_valid():
            raise ValueError(_("%(class)s is not valid") % {"class": type(self)})

        images = as_items_or_none(*get_autoimages_list())
        existing_slugs = [img["slug"] for img in images] if images else []
        self.is_update = self.cleaned_data.get("slug") in existing_slugs
        func = update_autoimage if self.is_update else add_autoimage

        success, autoimage_slug = func(
            slug=self.cleaned_data.get("slug"),
            config=self.cleaned_data.get("config").to_dict(),
            config_yaml=self.cleaned_data.get("config").builder.render(),
            contact_email=self.cleaned_data.get("contact_email"),
            periodicity="monthly",
            warehouse=self.cleaned_data.get("warehouse"),
            channel=self.cleaned_data.get("channel"),
            private=self.cleaned_data.get("private"),
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
            _("Unable to connect (HTTP %(code)s) to API at <code>%(url)s</code>%(msg)s")
            % {
                "url": settings.CARDSHOP_API_URL,
                "code": code,
                "msg": " -- " + msg if msg else "",
            },
        )
        return redirect("admin")

    context = {
        "channels": as_items_or_none(*get_channels_list()) or None,
        "warehouses": as_items_or_none(*get_warehouses_list()) or None,
        "users": as_items_or_none(*get_users_list()) or None,
        "workers": as_items_or_none(*get_workers_list()) or None,
        "images": as_items_or_none(*get_autoimages_list()) or None,
        "api_url": settings.CARDSHOP_API_URL_EXTERNAL,
    }
    # images is accessed several times
    if context["images"]:
        context["images"] = list(context["images"])

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
                messages.error(request, _("Error while saving… %(err)s") % {"err": exp})
            else:
                messages.success(request, context[form_key].success_message(res))
                return redirect("scheduler")

    if success:
        messages.set_level(request, messages.DEBUG)
        messages.info(
            request,
            _("Connected to Scheduler API at <code>%(url)s</code>")
            % {"url": settings.CARDSHOP_API_URL},
        )

    return render(request, "scheduler.html", context)


@staff_required
def channel_enable(request, channel_id):
    success, channel_id = enable_channel(channel_id)
    if not success:
        logger.error(f"Unable to enable channel: {channel_id}")
        messages.error(
            request,
            _("Unable to enable Channel: -- ref: %(channel_id)s")
            % {"channel_id": channel_id},
        )
    else:
        messages.success(
            request,
            _("Successfuly enabled channel: %(channel_id)s")
            % {"channel_id": channel_id},
        )

    return redirect("scheduler")


@staff_required
def channel_disable(request, channel_id):
    success, channel_id = disable_channel(channel_id)
    if not success:
        logger.error(f"Unable to disable channel: {channel_id}")
        messages.error(
            request,
            _("Unable to disable Channel: -- ref: %(channel_id)s")
            % {"channel_id": channel_id},
        )
    else:
        messages.success(
            request,
            _("Successfuly disabled channel: %(channel_id)s")
            % {"channel_id": channel_id},
        )

    return redirect("scheduler")


@staff_required
def warehouse_enable(request, warehouse_id):
    success, warehouse_id = enable_warehouse(warehouse_id)
    if not success:
        logger.error(f"Unable to enable warehouse: {warehouse_id}")
        messages.error(
            request,
            _("Unable to enable warehouse: -- ref: %(warehouse_id)s")
            % {"warehouse_id": warehouse_id},
        )
    else:
        messages.success(
            request,
            _("Successfuly enabled warehouse: %(warehouse_id)s")
            % {"warehouse_id": warehouse_id},
        )

    return redirect("scheduler")


@staff_required
def warehouse_disable(request, warehouse_id):
    success, warehouse_id = disable_warehouse(warehouse_id)
    if not success:
        logger.error(f"Unable to disable warehouse: {warehouse_id}")
        messages.error(
            request,
            _("Unable to disable warehouse: -- ref: %(warehouse_id)s")
            % {"warehouse_id": warehouse_id},
        )
    else:
        messages.success(
            request,
            _("Successfuly disabled warehouse: %(warehouse_id)s")
            % {"warehouse_id": warehouse_id},
        )

    return redirect("scheduler")


@staff_required
def user_enable(request, user_id):
    success, user_id = enable_user(user_id)
    if not success:
        logger.error(f"Unable to enable user: {user_id}")
        messages.error(
            request,
            _("Unable to enable user: -- ref: %(user_id)s") % {"user_id": user_id},
        )
    else:
        messages.success(
            request, _("Successfuly enabled user: %(user_id)s") % {"user_id": user_id}
        )

    return redirect("scheduler")


@staff_required
def user_disable(request, user_id):
    success, user_id = disable_user(user_id)
    if not success:
        logger.error(f"Unable to disable user: {user_id}")
        messages.error(
            request,
            _("Unable to disable user: -- ref: %(user_id)s") % {"user_id": user_id},
        )
    else:
        messages.success(
            request, _("Successfuly disabled user: %(user_id)s") % {"user_id": user_id}
        )

    return redirect("scheduler")


@staff_required
def refresh_token(request):
    authenticate(force=True)
    logger.info(f"Re-authenticated against the scheduler: `{ACCESS_TOKEN}`")
    messages.info(
        request,
        _("Re-authenticated against the scheduler: <code>%(token)s</code>")
        % {"token": ACCESS_TOKEN[:20]},
    )
    return redirect("scheduler")


@staff_required
def image_delete(request, image_slug):
    success, _resp = delete_autoimage(image_slug)
    if not success:
        logger.error(f"Unable to delete image: {image_slug}")
        messages.error(
            request,
            _("Unable to delete image: -- ref: %(slug)s") % {"slug": image_slug},
        )
    else:
        messages.success(
            request, _("Successfuly deleted image: %(slug)s") % {"slug": image_slug}
        )

    return redirect("scheduler")
