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
from django.utils.translation import (
    gettext as _,
    gettext_lazy as _lz,
    get_language_from_request,
)

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
            raise forms.ValidationError(_("Invalid Phone Number"), code="invalid")

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
            return _("Successfuly created Address <em>%(address)s</em>") % {
                "address": res
            }
        return _("Successfuly updated Address <em>%(address)s</em>") % {"address": res}


class OrderForm(forms.Form):
    KIND_CHOICES = {
        Media.VIRTUAL: _lz("Download Link"),
        Media.PHYSICAL: _lz("Physical micro-SD Card(s)"),
    }
    # VALIDITY_CHOICES = {x: "{} days".format(x * 5) for x in range(1, 11)}

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request")
        super().__init__(*args, **kwargs)
        self.client = request.user.profile
        self.request_lang = get_language_from_request(request)
        self.organization = self.client.organization
        self.fields["config"].choices = Configuration.get_choices(self.organization)
        self.fields["address"].choices = [("none", "Myself")] + Address.get_choices(
            self.organization
        )
        self.fields["media"].choices = Media.get_choices(
            kind=None if self.client.can_order_physical else Media.VIRTUAL,
            display_units=self.client.is_limited,
        )
        self.fields["kind"].choices = filter(
            lambda item: self.client.can_order_physical or item[0] != Media.PHYSICAL,
            self.KIND_CHOICES.items(),
        )

    kind = forms.ChoiceField(
        choices=[],
        label=_lz("Order Type"),
        help_text=_lz("Either download link sent via email or micro-SD card shipment"),
    )
    config = forms.ChoiceField(
        choices=[],
        label=_lz("Configuration"),
        help_text=_lz(
            "Missing your configuration? "
            "Go check your configurations list for any warning."
        ),
    )
    address = forms.ChoiceField(choices=[], label=_lz("Recipient"))
    media = forms.ChoiceField(
        choices=[],
        help_text=_lz(
            "You can choose larger media size to add free space to your hotspot"
        ),
    )
    quantity = forms.IntegerField(
        initial=1,
        min_value=1,
        max_value=10,
        help_text=_lz("Number of physical micro-SD cards you want"),
    )

    def VIRTUAL_CHOICES(self):
        return Media.get_choices(kind=Media.VIRTUAL)

    def PHYSICAL_CHOICES(self):
        return Media.get_choices(kind=Media.PHYSICAL)

    def clean_config(self):
        config = Configuration.get_or_none(self.cleaned_data.get("config"))
        if config is None or config.organization != self.organization:
            raise forms.ValidationError(_("Not your configuration"), code="invalid")
        return config

    def clean_address(self):
        if self.cleaned_data.get("address", "none") == "none":
            return
        address = Address.get_or_none(self.cleaned_data.get("address"))
        if address and address.organization != self.organization:
            raise forms.ValidationError(_("Not your address"), code="invalid")
        return address

    def clean_media(self):
        media = Media.get_or_none(self.cleaned_data.get("media"))
        if media is None:
            raise forms.ValidationError(_("Incorrect Media"), code="invalid")
        if media.kind == Media.PHYSICAL and not self.client.can_order_physical:
            raise forms.ValidationError(
                _("Not allowed to order physical"), code="invalid"
            )
        return media

    def clean_quantity(self):
        if self.cleaned_data.get("kind") == Media.VIRTUAL:
            return 1
        try:
            quantity = int(self.cleaned_data.get("quantity"))
        except Exception:
            raise forms.ValidationError(_("Incorrect quantity"), code="invalid")
        return quantity

    def clean(self):
        cleaned_data = super().clean()
        config = cleaned_data.get("config")
        media = cleaned_data.get("media")
        kind = cleaned_data.get("kind")
        address = cleaned_data.get("address")

        if kind == Media.PHYSICAL and (not address or not address.physical_compatible):
            self.add_error(
                "address", _("This address can't be used as it misses postal details")
            )

        if config is not None:
            # save config if its size changed
            if config.size_value_changed():
                config.save()

        if config is not None and media is not None and not config.can_fit_on(media):
            min_media = Media.get_min_for(config.size)
            if min_media is None:
                msg = _("There is no large enough Media for this config.")
                field = "config"
            else:
                msg = _(
                    "Media not large enough for config (use at least %(media)s)"
                ) % {"media": min_media.name}
                field = "media"
            self.add_error(field, msg)

    def save(self, *args, **kwargs):
        return Order.create_from(
            client=self.client,
            config=self.cleaned_data.get("config"),
            media=self.cleaned_data.get("media"),
            quantity=self.cleaned_data.get("quantity"),
            address=self.cleaned_data.get("address"),
            request_lang=self.request_lang,
        ).min_id

    @classmethod
    def success_message(cls, res):
        return _("Successfuly created Order <em>%(order)s</em>") % {"order": res}


class OrderShippingForm(forms.Form):
    def __init__(self, *args, **kwargs):
        order = kwargs.pop("order")
        super().__init__(*args, **kwargs)
        self.order = order

    details = forms.CharField(help_text=_lz("Shipment tracking details or similar"))

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
                    _(
                        "Failed to update your password although it looks OK. "
                        "ref: %(err)s"
                    )
                    % {"err": exp},
                )
            else:
                messages.success(request, _("Password Updated successfuly!"))
                update_session_auth_hash(request, form.user)
                return redirect("home")
    else:
        form = PasswordChangeForm(user=request.user)
    context["password_form"] = form
    return render(request, "password_change.html", context)


class EmailForm(forms.Form):
    email = forms.EmailField(label=_lz("E-mail address"))

    def clean_email(self):
        try:
            return Profile.get_using(self.cleaned_data.get("email"))
        except Exception:
            raise forms.ValidationError(_("No account for e-mail"), code="invalid")


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
                    subject=_("Imager Password Reset"),
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
                    _(
                        "Password reset validation code sent to "
                        "<code>%(email)s</code>"
                    )
                    % {"email": form.cleaned_data["email"].email},
                )
                return redirect("reset_password_confirm")
            except Exception as exc:
                logger.error(
                    f"Error sending password reset to {form.cleaned_data['email']}"
                )
                logger.exception(exc)
                messages.error(
                    request,
                    _(
                        "An error has occured trying to reset your password. "
                        "Please try again later: %(err)s"
                    )
                    % {"err": exc},
                )
                return redirect("reset_password")
    else:
        form = EmailForm()
    context["form"] = form
    return render(request, "password_reset.html", context)


class PasswordResetForm(forms.Form):
    code = forms.UUIDField(label=_lz("Validation Code"))
    password = forms.CharField(max_length=50, label=_lz("New Password"))

    def clean_code(self):
        prc = PasswordResetCode.get_or_none(self.cleaned_data.get("code"))
        if not prc:
            raise forms.ValidationError(_("Invalid validation code"), code="invalid")
        if prc.created_on + datetime.timedelta(days=1) < timezone.now():
            raise forms.ValidationError(_("Expired validation code"), code="invalid")
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
                messages.error(
                    request, _("Error updating your password: %(err)s") % {"err": exc}
                )
                return redirect("reset_password_confirm")
            try:
                prc.delete()
            except Exception as exc:
                logger.error(f"Failed to remove PRC: {exc}")
                logger.exception(exc)
            messages.success(request, _("Password Updated successfuly!"))
            return redirect("home")
    else:
        form = PasswordResetForm(initial=request.GET)
    context["form"] = form
    return render(request, "password_reset_confirm.html", context)


def do_delete_account(profile):
    """Remove all information for a particular user"""

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
                _("Failed to delete your account. (ref: %(err)s)") % {"err": exp},
            )
        else:
            messages.success(request, _("Account deleted successfuly!"))
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
        raise Http404(_("Address not found"))
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
                messages.error(request, _("Error while saving… %(err)s") % {"err": exp})
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
        raise Http404(_("Address not found"))

    if address.organization != request.user.profile.organization:
        return PermissionDenied()

    try:
        address.delete()
        messages.success(
            request,
            _("Successfuly deleted Address <em>%(address)s</em>")
            % {"address": address},
        )
    except Exception as exp:
        logger.error(f"Unable to delete Address {address.id}: {exp}")
        messages.error(
            request,
            _("Unable to delete Address <em>%(address)s</em>: -- ref %(err)s")
            % {"address": address, "err": exp},
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
            request, _("You need a Configuration to place an Order. Add one first!")
        )
        return redirect("configuration_list")

    # staff and admin are allowed to place multiple orders at once
    if request.user.is_staff or request.user.is_superuser:
        can_order = True
        previous_order_id = None
    else:
        previous_order_id = Order.profile_has_active(request.user.profile)
        can_order = not previous_order_id
    context.update({"can_order": can_order, "previous_order_id": previous_order_id})

    # display an alert informing user he cannot order at the moment
    # if he had just clicked on Order, using an error message and blocking the process
    # otherwise a warning is enough
    if not context["can_order"]:
        func = getattr(messages, "error" if request.method == "POST" else "warning")
        func(
            request,
            _(
                "Your previous Order (#%(order_id)s) must complete "
                "before you're allowed to request a new one."
            )
            % {"order_id": previous_order_id},
        )

    form = OrderForm(request=request)
    if request.method == "POST" and can_order:

        # which form is being saved?
        form = OrderForm(request.POST, request=request)
        if form.is_valid():
            try:
                res = form.save()
            except Exception as exp:
                logger.error(exp)
                messages.error(request, _("Error while saving… %(err)s") % {"err": exp})
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
        raise Http404(
            _("Order with ID `%(order_id)s` not found") % {"order_id": order_min_id}
        )

    context = {"order": order}
    return render(request, "order.html", context)


@login_required
def order_detail_scheduler_id(request, order_id):
    order = Order.get_by_scheduler_id(order_id)
    if order is None:
        raise Http404(
            _("Order with Scheduler ID `%(order_id)s` not found")
            % {"order_id": order_id}
        )

    return redirect("order_detail", order_min_id=order.min_id)


@login_required
def order_cancel(request, order_min_id):
    order = Order.get_or_none(order_min_id)
    if order is None:
        raise Http404(
            _("Order with ID `%(order_id)s` not found") % {"order_id": order_min_id}
        )

    if order.cancel():
        messages.success(
            request,
            _("Successfuly canceled order #%(order_id)s") % {"order_id": order_min_id},
        )
    else:
        messages.error(
            request,
            _("Unable to cancel order #%(order_id)s") % {"order_id": order_min_id},
        )

    return redirect("order_detail", order_min_id=order.min_id)


def order_add_shipping(request, order_id):
    order = Order.get_by_scheduler_id(order_id)

    if order.data.status != "pending_shipment":
        raise Http404(
            _("Order %(order_id)s is not pending_shipment") % {"order_id": order.min_id}
        )

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
                    _("Failed to record shipping informations.. (ref: %(err)s)")
                    % {"err": exp},
                )
            else:
                messages.success(request, _("Order Shipping informations recorded!"))
                return redirect("order_detail", order_min_id=order.min_id)
    else:
        form = OrderShippingForm(order=order)
    context["form"] = form

    return render(request, "add_shipping.html", context)
