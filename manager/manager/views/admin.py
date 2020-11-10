#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging

from django import forms
from django.http import Http404
from django.contrib import messages
from django.shortcuts import render, redirect

from manager.decorators import staff_required
from manager.models import Organization, Profile, Media
from manager.views.ui import do_delete_account

logger = logging.getLogger(__name__)


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = [
            "slug",
            "name",
            "channel",
            "warehouse",
            "public_warehouse",
            "email",
            "units",
        ]

    @staticmethod
    def success_message(result):
        return "Successfuly created Organization <em>{org}</em>".format(org=result)


def get_orgs():
    return [(org.slug, org.name) for org in Organization.objects.all()]


class UpdateUnitsForm(forms.Form):
    organization = forms.ChoiceField(choices=get_orgs)
    units = forms.IntegerField(required=False)

    @staticmethod
    def success_message(result):
        return "Successfuly updated units for <em>{org}</em>".format(org=result)

    def clean_organization(self):
        if Organization.get_or_none(self.cleaned_data.get("organization")) is None:
            raise forms.ValidationError("Not a valid Organization", code="invalid")
        return self.cleaned_data.get("organization")

    def save(self):
        if not self.is_valid():
            raise ValueError("{cls} is not valid".format(cls=type(self)))

        organization = Organization.get_or_none(self.cleaned_data.get("organization"))
        organization.units = self.cleaned_data.get("units")
        organization.save()
        return organization


class ProfileForm(forms.Form):
    organization = forms.ChoiceField(choices=get_orgs)
    name = forms.CharField(max_length=100)
    email = forms.EmailField()
    username = forms.CharField(max_length=100)
    password = forms.CharField(max_length=100)
    is_admin = forms.BooleanField(initial=False, label="admin?", required=False)
    can_sd = forms.BooleanField(initial=False, label="SD?", required=False)

    @staticmethod
    def success_message(result):
        return "Successfuly created Manager User <em>{user}</em>".format(user=result)

    def clean_username(self):
        if Profile.exists(username=self.cleaned_data.get("username")):
            raise forms.ValidationError("Username is already taken.", code="invalid")
        return self.cleaned_data.get("username")

    def clean_email(self):
        if Profile.taken(email=self.cleaned_data.get("email")):
            raise forms.ValidationError("Email is already in use.", code="invalid")
        return self.cleaned_data.get("email")

    def clean_organization(self):
        if Organization.get_or_none(self.cleaned_data.get("organization")) is None:
            raise forms.ValidationError("Not a valid Organization", code="invalid")
        return self.cleaned_data.get("organization")

    def save(self):
        if not self.is_valid():
            raise ValueError("{cls} is not valid".format(cls=type(self)))

        organization = Organization.get_or_none(self.cleaned_data.get("organization"))
        return Profile.create(
            organization=organization,
            first_name=self.cleaned_data.get("name").strip(),
            email=self.cleaned_data.get("email"),
            username=self.cleaned_data.get("username"),
            password=self.cleaned_data.get("password"),
            is_admin=self.cleaned_data.get("is_admin"),
            can_order_physical=self.cleaned_data.get("can_sd"),
            expiry=None,
        )


class MediaForm(forms.ModelForm):
    class Meta:
        model = Media
        fields = ["name", "kind", "size", "units_coef"]

    @staticmethod
    def success_message(result):
        return "Successfuly created Media <em>{media}</em>".format(media=result)


@staff_required
def dashboard(request):
    context = {
        "organizations": Organization.objects.all(),
        "profiles": Profile.objects.all(),
        "medias": Media.objects.all(),
    }

    forms_map = {
        "org_form": OrganizationForm,
        "profile_form": ProfileForm,
        "media_form": MediaForm,
        "units_form": UpdateUnitsForm,
    }

    # assume GET
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
                return redirect("admin")
    else:
        pass

    return render(request, "admin.html", context)


@staff_required
def toggle_account(request, username):

    profile = Profile.get_or_none(username)
    if profile is None:
        raise Http404("Profile not found")

    profile.user.is_active = not profile.user.is_active
    status = "enabled" if profile.user.is_active else "disabled"
    try:
        profile.user.save()
    except Exception as exp:
        logger.error(exp)
        messages.error(
            request,
            "User Account for {user} could not be {status}. (ref: {exp})".format(
                user=profile, status=status, exp=exp
            ),
        )
    else:
        messages.success(
            request,
            "User Account for {user} has been successfuly {status}.".format(
                user=profile, status=status
            ),
        )

    return redirect("admin")


@staff_required
def delete_account(request, username):

    profile = Profile.get_or_none(username)
    if profile is None:
        raise Http404("Profile not found")

    user_repr = str(profile)

    try:
        do_delete_account(profile)
    except Exception as exp:
        logger.error(exp)
        messages.error(
            request,
            f"Error while deleting {user_repr}. Please contact support (ref: {exp})",
        )
    else:
        messages.success(
            request,
            f"User Account for {user_repr} has been successfuly deleted.",
        )

    return redirect("admin")
