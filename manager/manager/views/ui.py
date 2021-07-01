#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging
import datetime

from django import forms
from django.http import Http404
from django.conf import settings
from django.utils import timezone
from django.template import loader
from django.contrib import messages
from django.contrib.auth import logout
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.core.exceptions import PermissionDenied
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required

from manager.models import (
    Address,
    Media,
    Configuration,
    Order,
    Profile,
    PasswordResetCode,
)
from manager.email import send_mailgun_email
from manager.scheduler import add_order_shipment, anonymize_orders, SchedulerAPIError

logger = logging.getLogger(__name__)
NB_ORDERS_PER_PAGE = 10
NB_ADDRESSES_PER_PAGE = 10


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ["name", "recipient", "email", "phone", "address", "country"]

    def __init__(self, *args, **kwargs):
        client = kwargs.pop("client")
        super().__init__(*args, **kwargs)
        self.organization = client.organization
        self.created_by = client

    def clean_phone(self):
        if not self.cleaned_data.get("phone"):
            return self.cleaned_data.get("phone")
        try:
            cleaned_phone = Address.cleaned_phone(self.cleaned_data.get("phone"))
        except Exception as exp:
            logger.error(exp)
            logger.exception(exp)
            raise forms.ValidationError("Invalid Phone Number", code="invalid")

        return cleaned_phone

    def clean_address(self):
        return self.cleaned_data.get("address").strip()

    def save(self, *args, **kwargs):
        instance = super().save(commit=False)
        instance.organization = self.organization
        instance.created_by = self.created_by
        instance.save()
        return instance

    @classmethod
    def success_message(cls, res, created):
        if created:
            return "Successfuly created Address <em>{}</em>".format(res)
        return "Successfuly updated Address <em>{}</em>".format(res)


class OrderForm(forms.Form):
    KIND_CHOICES = {
        Media.VIRTUAL: "Download Link",
        Media.PHYSICAL: "Physical micro-SD Card(s)",
    }
    # VALIDITY_CHOICES = {x: "{} days".format(x * 5) for x in range(1, 11)}

    def __init__(self, *args, **kwargs):
        client = kwargs.pop("client")
        super().__init__(*args, **kwargs)
        self.client = client
        self.organization = client.organization
        self.fields["config"].choices = Configuration.get_choices(self.organization)
        self.fields["address"].choices = [("none", "Myself")] + Address.get_choices(
            self.organization
        )
        self.fields["media"].choices = Media.get_choices(
            kind=None if client.can_order_physical else Media.VIRTUAL,
            display_units=client.is_limited,
        )
        self.fields["kind"].choices = filter(
            lambda item: client.can_order_physical or item[0] != Media.PHYSICAL,
            self.KIND_CHOICES.items(),
        )

    kind = forms.ChoiceField(
        choices=[],
        label="Order Type",
        help_text="Either download link sent via email or micro-SD card shipment",
    )
    config = forms.ChoiceField(choices=[], label="Configuration")
    address = forms.ChoiceField(choices=[], label="Recipient")
    media = forms.ChoiceField(
        choices=[],
        help_text="You can choose larger media size to add free space to your hotspot",
    )
    quantity = forms.IntegerField(
        initial=1,
        min_value=1,
        max_value=10,
        help_text="Number of physical micro-SD cards you want",
    )

    def VIRTUAL_CHOICES(self):
        return Media.get_choices(kind=Media.VIRTUAL)

    def PHYSICAL_CHOICES(self):
        return Media.get_choices(kind=Media.PHYSICAL)

    def clean_config(self):
        config = Configuration.get_or_none(self.cleaned_data.get("config"))
        if config is None or config.organization != self.organization:
            raise forms.ValidationError("Not your configuration", code="invalid")
        return config

    def clean_address(self):
        if self.cleaned_data.get("address", "none") == "none":
            return
        address = Address.get_or_none(self.cleaned_data.get("address"))
        if address and address.organization != self.organization:
            raise forms.ValidationError("Not your address", code="invalid")
        return address

    def clean_media(self):
        media = Media.get_or_none(self.cleaned_data.get("media"))
        if media is None:
            raise forms.ValidationError("Incorrect Media", code="invalid")
        if media.kind == Media.PHYSICAL and not self.client.can_order_physical:
            raise forms.ValidationError("Not allowed to order physical", code="invalid")
        return media

    def clean_quantity(self):
        if self.cleaned_data.get("kind") == Media.VIRTUAL:
            return 1
        try:
            quantity = int(self.cleaned_data.get("quantity"))
        except Exception:
            raise forms.ValidationError("Incorrect quantity", code="invalid")
        return quantity

    def clean(self):
        cleaned_data = super().clean()
        config = cleaned_data.get("config")
        media = cleaned_data.get("media")
        kind = cleaned_data.get("kind")
        address = cleaned_data.get("address")

        if kind == Media.PHYSICAL and (not address or not address.physical_compatible):
            self.add_error(
                "address", "This address can't be used as it misses postal details"
            )

        if config is not None:
            # save config if its size changed
            if config.size_value_changed():
                config.save()

        if config is not None and media is not None and not config.can_fit_on(media):
            min_media = Media.get_min_for(config.size)
            if min_media is None:
                msg = "There is no large enough Media for this config."
                field = "config"
            else:
                msg = "Media not large enough for config (use at least {})".format(
                    min_media.name
                )
                field = "media"
            self.add_error(field, msg)

    def save(self, *args, **kwargs):
        return Order.create_from(
            client=self.client,
            config=self.cleaned_data.get("config"),
            media=self.cleaned_data.get("media"),
            quantity=self.cleaned_data.get("quantity"),
            address=self.cleaned_data.get("address"),
        ).min_id

    @classmethod
    def success_message(cls, res):
        return "Successfuly created Order <em>{}</em>".format(res)


class OrderShippingForm(forms.Form):
    def __init__(self, *args, **kwargs):
        order = kwargs.pop("order")
        super().__init__(*args, **kwargs)
        self.order = order

    details = forms.CharField(help_text="Shipment tracking details or similar")

    def save(self, *args, **kwargs):
        success, response = add_order_shipment(
            order_id=self.order.scheduler_id,
            shipment_details=self.cleaned_data.get("details"),
        )
        if not success:
            raise SchedulerAPIError(response)


@login_required
def home(request):
    context = {"support_email": settings.SUPPORT_EMAIL}
    return render(request, "home.html", context)


@login_required
def password_change(request):
    context = {}
    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            try:
                form.save()
            except Exception as exp:
                logger.error(exp)
                messages.error(
                    request,
                    f"Failed to update your password although it looks OK. ref: {exp}",
                )
            else:
                messages.success(request, "Password Updated successfuly !")
                update_session_auth_hash(request, form.user)
                return redirect("home")
    else:
        form = PasswordChangeForm(user=request.user)
    context["password_form"] = form
    return render(request, "password_change.html", context)


class EmailForm(forms.Form):
    email = forms.EmailField(label="E-mail address")

    def clean_email(self):
        try:
            return Profile.get_using(self.cleaned_data.get("email"))
        except Exception:
            raise forms.ValidationError("No account for e-mail", code="invalid")


def password_reset(request):
    context = {}
    if request.method == "POST":
        form = EmailForm(data=request.POST)
        if form.is_valid():
            try:
                prc = PasswordResetCode.objects.create(
                    profile=form.cleaned_data["email"]
                )
                send_mailgun_email(
                    to=prc.profile.email,
                    subject="Cardshop Password Reset",
                    contents=loader.render_to_string(
                        "password_reset_email.html",
                        {
                            "prc": prc,
                            "CARDSHOP_PUBLIC_URL": settings.CARDSHOP_PUBLIC_URL,
                        },
                    ),
                )

                messages.info(
                    request,
                    f"Password reset validation code sent to "
                    f"<code>{form.cleaned_data['email'].email}</code>",
                )
                return redirect("reset_password_confirm")
            except Exception as exc:
                logger.error(
                    f"Error sending password reset to {form.cleaned_data['email']}"
                )
                logger.exception(exc)
                messages.error(
                    request,
                    f"An error has occured trying to reset your password. "
                    f"Please try again later: {exc}",
                )
                return redirect("reset_password")
    else:
        form = EmailForm()
    context["form"] = form
    return render(request, "password_reset.html", context)


class PasswordResetForm(forms.Form):
    code = forms.UUIDField(label="Validation Code")
    password = forms.CharField(max_length=50, label="New Password")

    def clean_code(self):
        prc = PasswordResetCode.get_or_none(self.cleaned_data.get("code"))
        if not prc:
            raise forms.ValidationError("Invalid validation code", code="invalid")
        if prc.created_on + datetime.timedelta(days=1) < timezone.now():
            raise forms.ValidationError("Expired validation code", code="invalid")
        return prc


def password_reset_confirm(request):
    context = {}
    if request.method == "POST":
        form = PasswordResetForm(data=request.POST)
        if form.is_valid():
            prc = form.cleaned_data.get("code")
            try:
                prc.profile.user.set_password(form.cleaned_data.get("password"))
                prc.profile.user.save()
            except Exception as exc:
                logger.error(f"Failed to reset password for {prc}")
                logger.exception(exc)
                messages.error(request, f"Error updating your password: {exc}")
                return redirect("reset_password_confirm")
            try:
                prc.delete()
            except Exception as exc:
                logger.error(f"Failed to remove PRC: {exc}")
                logger.exception(exc)
            messages.success(request, "Password Updated successfuly !")
            return redirect("home")
    else:
        form = PasswordResetForm(initial=request.GET)
    context["form"] = form
    return render(request, "password_reset_confirm.html", context)


def do_delete_account(profile):
    """ Remove all information for a particular user """

    # clean-up details on all orders created by user
    order_ids = [p.scheduler_id for p in profile.order_set.all()]
    for order in profile.order_set.all():
        if order.status == order.IN_PROGRESS:
            order.cancel()
        order.anonymize()

    # delete django user, will cascade to Profile, Address and Configuration
    profile.user.delete()

    # request anonymization of orders on API
    success, response = anonymize_orders(order_ids)
    if not success:
        raise SchedulerAPIError(response)


@login_required
def delete_account(request):
    context = {}
    if request.method == "POST":
        try:
            do_delete_account(request.user.profile)
        except Exception as exp:
            logger.error(exp)
            messages.error(
                request,
                "Failed to delete your account. (ref: {exp})".format(exp=exp),
            )
        else:
            messages.success(request, "Account deleted successfuly !")
            logout(request)
        return redirect("home")
    return render(request, "delete_account.html", context)


@login_required
def address_list(request):

    page = request.GET.get("page")

    address_filter = bool(request.GET.get("all", False) == "yes")
    filtered_addresses = Address.objects.filter(
        organization=request.user.profile.organization
    )

    if not address_filter:
        filtered_addresses = filtered_addresses.filter(created_by=request.user.profile)

    paginator = Paginator(filtered_addresses, NB_ADDRESSES_PER_PAGE)

    addresses_page = paginator.get_page(page)

    context = {
        "address_filter": address_filter,
        "addresses_page": addresses_page,
        "addresses": addresses_page.object_list,
    }

    return render(request, "address_list.html", context)


@login_required
def address_edit(request, address_id=None):

    address = Address.get_or_none(address_id)
    if address is None and address_id is not None:
        raise Http404("Address not found")
    if (
        address is not None
        and address.organization != request.user.profile.organization
    ):
        return PermissionDenied()

    context = {"address": address}
    form = AddressForm(client=request.user.profile, instance=address)

    if request.method == "POST":
        form = AddressForm(request.POST, instance=address, client=request.user.profile)
        if form.is_valid():
            try:
                res = form.save()
            except Exception as exp:
                import traceback

                print(traceback.format_exc())
                logger.error(exp)
                messages.error(request, "Error while saving… {exp}".format(exp=exp))
            else:
                messages.success(request, form.success_message(res, not bool(address)))
                return redirect("address_list")
    else:
        pass
    context["form"] = form

    return render(request, "address_edit.html", context)


@login_required
def address_delete(request, address_id=None):

    address = Address.get_or_none(address_id)
    if address is None:
        raise Http404("Address not found")

    if address.organization != request.user.profile.organization:
        return PermissionDenied()

    try:
        address.delete()
        messages.success(
            request, "Successfuly deleted Address <em>{}</em>".format(address)
        )
    except Exception as exp:
        logger.error(
            "Unable to delete Address {id}: {exp}".format(id=address.id, exp=exp)
        )
        messages.error(
            request,
            "Unable to delete Address <em>{addr}</em>: -- ref {exp}".format(
                addr=address, exp=exp
            ),
        )

    return redirect("address_list")


@login_required
def order_list(request):
    # query args
    page = request.GET.get("page")
    order_filter = (
        request.GET.get("only")
        if request.GET.get("only") in Order.STATUSES.keys()
        else Order.IN_PROGRESS
    )

    filtered_orders = Order.objects.filter(
        organization=request.user.profile.organization, status=order_filter
    )
    paginator = Paginator(filtered_orders, NB_ORDERS_PER_PAGE)
    orders_page = paginator.get_page(page)

    context = {
        "order_filter": order_filter,
        "orders_page": orders_page,
        "orders": orders_page.object_list,
    }

    return render(request, "order_list.html", context)


@login_required
def order_new(request, kind=Media.VIRTUAL):
    context = {
        "addresses": Address.objects.filter(
            organization=request.user.profile.organization
        ),
        "configurations": Configuration.objects.filter(
            organization=request.user.profile.organization
        ),
        "medias": Media.objects.all(),
        "LINK_VALIDITY_DAYS": Media.EXPIRATION_DELAY,
    }

    # can't order without a config
    if not context["configurations"].count():
        messages.warning(
            request, "You need a Configuration to place an Order. Add one first!"
        )
        return redirect("configuration_list")

    form = OrderForm(client=request.user.profile)
    if request.method == "POST":

        # which form is being saved?
        form = OrderForm(request.POST, client=request.user.profile)
        if form.is_valid():
            try:
                res = form.save()
            except Exception as exp:
                logger.error(exp)
                messages.error(request, "Error while saving… {exp}".format(exp=exp))
            else:
                messages.success(request, form.success_message(res))
                return redirect("order_list")
    else:
        pass
    context["form"] = form

    return render(request, "order_new.html", context)


@login_required
def order_detail(request, order_min_id):
    order = Order.get_or_none(order_min_id)
    if order is None:
        raise Http404("Order with ID `{}` not found".format(order_min_id))

    context = {"order": order}
    return render(request, "order.html", context)


def order_detail_scheduler_id(request, order_id):
    order = Order.get_by_scheduler_id(order_id)
    if order is None:
        raise Http404("Order with Scheduler ID `{}` not found".format(order_id))

    return redirect("order_detail", order_min_id=order.min_id)


def order_cancel(request, order_min_id):
    order = Order.get_or_none(order_min_id)
    if order is None:
        raise Http404("Order with ID `{}` not found".format(order_min_id))

    if order.cancel():
        messages.success(request, "Successfuly canceled order #{}".format(order_min_id))
    else:
        messages.error(request, "Unable to cancel order #{}".format(order_min_id))

    return redirect("order_detail", order_min_id=order.min_id)


def order_add_shipping(request, order_id):
    order = Order.get_by_scheduler_id(order_id)

    if order.data.status != "pending_shipment":
        raise Http404("Order {} is not pending_shipment".format(order.min_id))

    context = {"order": order}

    if request.method == "POST":
        form = OrderShippingForm(order=order, data=request.POST)
        if form.is_valid():
            try:
                form.save()
            except Exception as exp:
                logger.error(exp)
                messages.error(
                    request,
                    "Failed to record shipping informations.. (ref: {exp})".format(
                        exp=exp
                    ),
                )
            else:
                messages.success(request, "Order Shipping informations recorded!")
                return redirect("order_detail", order_min_id=order.min_id)
    else:
        form = OrderShippingForm(order=order)
    context["form"] = form

    return render(request, "add_shipping.html", context)
