#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging

from django import forms
from django.http import Http404
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required

from manager.models import Address, Media, Configuration, Order
from manager.scheduler import add_order_shipment, SchedulerAPIError

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
        try:
            cleaned_phone = AddressForm.clean_phone(self.cleaned_data.get("phone"))
        except Exception as exp:
            logger.error(exp)
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
    VALIDITY_CHOICES = {x: "{} days".format(x * 5) for x in range(1, 11)}

    def __init__(self, *args, **kwargs):
        client = kwargs.pop("client")
        super().__init__(*args, **kwargs)
        self.client = client
        self.organization = client.organization
        self.fields["config"].choices = Configuration.get_choices(self.organization)
        self.fields["address"].choices = Address.get_choices(self.organization)
        self.fields["media"].choices = Media.get_choices()

    kind = forms.ChoiceField(
        choices=KIND_CHOICES.items(),
        label="Order Type",
        help_text="Either download link sent via email or micro-SD card shipment",
    )
    config = forms.ChoiceField(choices=[], label="Configuration")
    address = forms.ChoiceField(choices=[], label="Recipient")
    media = forms.ChoiceField(
        choices=[],
        help_text="You can choose larger media size to add free space to your hotspot",
    )
    quantity = forms.ChoiceField(
        choices=VALIDITY_CHOICES.items(),
        label="Quantity / Link validity",
        help_text="Order copies or your Card or extend your download period",
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
        address = Address.get_or_none(self.cleaned_data.get("address"))
        if address is None or address.organization != self.organization:
            raise forms.ValidationError("Not your address", code="invalid")
        return address

    def clean_media(self):
        media = Media.get_or_none(self.cleaned_data.get("media"))
        if media is None:
            raise forms.ValidationError("Incorrect Media", code="invalid")
        return media

    def clean_quantity(self):
        try:
            quantity = int(self.cleaned_data.get("quantity"))
        except Exception:
            raise forms.ValidationError("Incorrect quantity", code="invalid")
        return quantity

    def clean(self):
        cleaned_data = super().clean()
        config = cleaned_data.get("config")
        media = cleaned_data.get("media")

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
    return render(request, "password_change.html", context)


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
    elif (
        address is not None
        and address.organization != request.user.profile.organization
    ):
        raise HttpResponse("Unauthorized", status=401)

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
        raise HttpResponse("Unauthorized", status=401)

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
        "validity_choices": OrderForm.VALIDITY_CHOICES.items(),
    }

    form = OrderForm(client=request.user.profile)
    if request.method == "POST":

        # which form is being saved?
        form = OrderForm(request.POST, client=request.user.profile)
        if form.is_valid():
            try:
                res = form.save()
            except Exception as exp:
                import traceback

                print(traceback.format_exc())
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
