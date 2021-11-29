#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import json
import logging

from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _

from manager.models import Configuration
from manager.pibox.packages import PACKAGES_LANGS

logger = logging.getLogger(__name__)

NB_CONFIGURATIONS_PER_PAGE = 10


class JSONUploadForm(forms.Form):
    file = forms.FileField(
        widget=forms.FileInput(attrs={"class": "form-control form-check-input btn-sm"})
    )


class ConfigurationForm(forms.ModelForm):
    class Meta:
        model = Configuration
        fields = [
            "name",
            "project_name",
            "language",
            "timezone",
            "wifi_password",
            "admin_account",
            "admin_password",
            "branding_logo",
            "branding_favicon",
            "branding_css",
            "content_zims",
            "content_kalite_fr",
            "content_kalite_en",
            "content_kalite_es",
            "content_wikifundi_fr",
            "content_wikifundi_en",
            "content_wikifundi_es",
            "content_aflatoun",
            "content_edupi",
            "content_edupi_resources",
            "content_nomad",
            "content_mathews",
            "content_africatik",
        ]


def handle_uploaded_json(fd):
    try:
        payload = fd.read()
        if type(payload) is bytes:
            payload = payload.decode("UTF-8")
        return json.loads(payload)
    except Exception:
        raise
        return None


@login_required
def configuration_list(request):

    page = request.GET.get("page")
    config_filter = bool(request.GET.get("all", False) == "yes")
    filtered_configurations = Configuration.objects.filter(
        organization=request.user.profile.organization
    )

    if not config_filter:
        filtered_configurations = filtered_configurations.filter(
            updated_by=request.user.profile
        )

    paginator = Paginator(filtered_configurations, NB_CONFIGURATIONS_PER_PAGE)
    configurations_page = paginator.get_page(page)

    context = {
        "configurations": configurations_page.object_list,
        "configurations_page": configurations_page,
        "config_filter": config_filter,
    }

    if request.method == "POST":
        form = JSONUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                js_config = handle_uploaded_json(request.FILES["file"])
            except Exception:
                messages.error(
                    request, _("Your file is not a valid JSON. Can't import it.")
                )
            else:
                try:
                    config = Configuration.create_from(
                        config=js_config or {}, author=request.user.profile
                    )
                except Exception as exp:
                    messages.error(
                        request,
                        _(
                            "An error occured while trying to import your config file. "
                            "Please retry or contact support. (ref: %(err)s)"
                        )
                        % {"err": exp},
                    )
                else:
                    return redirect("configuration_edit", config.id)
        else:
            pass
    else:
        form = JSONUploadForm()

    context["form"] = form

    return render(request, "configuration_list.html", context)


@login_required
def configuration_edit(request, config_id=None):
    context = {}

    if config_id:
        config = Configuration.get_or_none(config_id)
        if config is None:
            raise Http404(_("Configuration not found"))

        if config.organization != request.user.profile.organization:
            raise PermissionDenied()
    else:
        # new config
        config = Configuration(organization=request.user.profile.organization)

    # list of languages availables in all catalogs
    context["packages_langs"] = PACKAGES_LANGS

    if request.method == "POST":
        form = ConfigurationForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            try:
                instance = form.save(commit=False)
                instance.updated_by = request.user.profile
                instance.save()
            except Exception as exp:
                messages.error(
                    request,
                    _(
                        "Failed to save your configuration (although it looks good). "
                        "Try again and contact support "
                        "if it happens again (ref: $(err)s)"
                    )
                    % {"err": exp},
                )
            else:
                messages.success(request, _("Configuration Updated successfuly !"))
                return redirect("configuration_edit", config.id)
        else:
            pass
    else:
        form = ConfigurationForm(instance=config)

    context["form"] = form

    return render(request, "configuration_edit.html", context)


@login_required
def configuration_export(request, config_id=None):

    config = Configuration.get_or_none(config_id)
    if config is None:
        raise Http404(_("Configuration not found"))

    if config.organization != request.user.profile.organization:
        raise PermissionDenied()

    response = JsonResponse(
        config.to_dict(), safe=False, json_dumps_params={"indent": 4}
    )
    response["Content-Disposition"] = 'attachment; filename="{}.json"'.format(
        config.display_name
    )
    return response


@login_required
def configuration_delete(request, config_id=None):

    config = Configuration.get_or_none(config_id)
    if config is None:
        raise Http404("Configuration not found")

    if config.organization != request.user.profile.organization:
        raise PermissionDenied()

    try:
        config.delete()
        messages.success(
            request,
            _("Successfuly deleted Configuration <em>%(config)s</em>")
            % {"config": config},
        )
    except Exception as exp:
        logger.error(
            "Unable to delete configuration {id}: {exp}".format(id=config.id, exp=exp)
        )
        messages.error(
            request,
            _("Unable to delete Configuration <em>%(config)s</em>: -- ref %(err)s")
            % {"config": config, "err": exp},
        )

    return redirect("configuration_list")


@login_required
def configuration_duplicate(request, config_id=None):

    config = Configuration.get_or_none(config_id)
    if config is None:
        raise Http404(_("Configuration not found"))

    if config.organization != request.user.profile.organization:
        raise PermissionDenied()

    try:
        nconfig = config.duplicate(by=request.user.profile)
        messages.success(
            request,
            _(
                "Successfuly duplicated Configuration <em>%(config)s</em> "
                "into <em>%(new_config)s</em>"
            )
            % {"config": config, "new_config": nconfig},
        )
    except Exception as exp:
        logger.error(
            "Unable to duplicate configuration {id}: {exp}".format(
                id=config.id, exp=exp
            )
        )
        messages.error(
            request,
            _("Unable to duplicate Configuration <em>%(config)s</em>: -- ref %(err)s")
            % {"config": config, "err": exp},
        )

    return redirect("configuration_list")
