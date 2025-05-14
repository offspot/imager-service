#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 nu

import json
import logging

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from offspot_config.catalog import app_catalog

from manager.kiwix_library import catalog
from manager.models import Configuration

logger = logging.getLogger(__name__)

NB_CONFIGURATIONS_PER_PAGE = 20


class JSONUploadForm(forms.Form):
    file = forms.FileField(
        widget=forms.FileInput(
            attrs={
                "class": "form-control form-check-input btn-sm",
                "accept": "application/json,text/plain,text/json",
            }
        )
    )


class ConfigurationForm(forms.ModelForm):
    class Meta:
        model = Configuration
        fields = [  # noqa: RUF012
            "name",
            "ssid",
            "project_name",
            "language",
            "timezone",
            "wifi_password",
            "admin_account",
            "admin_password",
            "branding_logo",
            "branding_favicon",
            "content_zims",
            "content_packages",
            "content_edupi_resources",
            "content_metrics",
            "option_kiwix_readers",
            "beta_features",
            "updated_by",
        ]

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get(
            "content_edupi_resources", False
        ) and "file-manager.offspot.kiwix.org" not in cleaned_data.get(
            "content_packages", []
        ):
            self.add_error(
                "content_edupi_resources",
                ValidationError(
                    _("Enable File Manager to use a preloading file URL"),
                    code="invalid_nofm",
                ),
            )
        return cleaned_data


def handle_uploaded_json(fd):
    try:
        payload = fd.read()
        if isinstance(payload, bytes):
            payload = payload.decode("UTF-8")
        return json.loads(payload)
    except Exception:
        raise
        return None


@login_required
def configuration_list(request):
    page = request.GET.get("page")
    config_filter = bool(request.GET.get("all", False) == "yes")
    sort_field = request.GET.get("sort", "updated_on")
    sort_dir = request.GET.get("dir", "desc")
    filtered_configurations = Configuration.objects.filter(
        organization=request.user.profile.organization
    )
    if not config_filter:
        filtered_configurations = filtered_configurations.filter(
            updated_by=request.user.profile
        )
    filtered_configurations = apply_config_sorting(
        filtered_configurations, sort_field, sort_dir
    )
    paginator = Paginator(filtered_configurations, NB_CONFIGURATIONS_PER_PAGE)
    configurations_page = paginator.get_page(page)
    context = {
        "configurations": configurations_page.object_list,
        "configurations_page": configurations_page,
        "config_filter": config_filter,
        "sort_field": sort_field,
        "sort_dir": sort_dir,
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
                    logger.exception(exp)
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


# sorting function for configurations
def apply_config_sorting(queryset, sort_field, sort_dir):
    """Apply sorting to configuration queryset."""
    order_prefix = "" if sort_dir == "asc" else "-"
    if sort_field == "name":
        return queryset.order_by(f"{order_prefix}name")
    elif sort_field == "updated_by":
        return queryset.order_by(f"{order_prefix}updated_by__user__first_name")
    elif sort_field in ("size", "min_media", "updated_on"):
        sort_field = "size" if sort_field == "min_media" else sort_field
        return queryset.order_by(f"{order_prefix}{sort_field}")
    else:
        return queryset.order_by("-updated_on")


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
        config = Configuration(
            organization=request.user.profile.organization,
            updated_by=request.user.profile,
        )

    context["is_new"] = config_id is None

    # list of languages availables in all catalogs
    context["packages_langs"] = catalog.languages

    context["tab"] = "general"  # default
    context["lang_filter"] = None

    if request.method == "POST":
        if request.POST.get("tab", "").strip() in (
            "general",
            "branding",
            "files",
            "zims",
            "apps",
        ):
            context["tab"] = request.POST["tab"].strip()

        if request.POST.get("lang_filter", "").strip():
            context["lang_filter"] = request.POST["lang_filter"].strip()[:3]

        form = ConfigurationForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            try:
                instance = form.save(commit=False)
                instance.updated_by = request.user.profile
                if not request.user.profile.can_brand:
                    instance.project_name = settings.DEFAULT_DOMAIN
                    instance.ssid = settings.DEFAULT_SSID
                    instance.branding_logo = None
                    instance.branding_favicon = None
                instance.save()
            except Exception as exp:
                logger.exception(exp)
                messages.error(
                    request,
                    _(
                        "Failed to save your configuration (although it looks good). "
                        "Try again and contact support "
                        "if it happens again (ref: %(err)s)"
                    )
                    % {"err": exp},
                )
            else:
                if request.POST.get("order-on-success"):
                    return redirect("configuration_order", config_id=config.id)
                messages.success(request, _("Configuration Updated successfuly !"))
        else:
            pass
    else:
        form = ConfigurationForm(instance=config)

    context["CATALOG_URL"] = catalog.final_catalog_url
    context["DEMO_URL"] = "https://browse.library.kiwix.org"
    context["languages"] = catalog.languages
    context["app_catalog"] = app_catalog
    context["form"] = form
    context["missing_zims"] = config.retrieve_missing_zims()
    context["config_id"] = config.id
    context["BETA_FEATURES"] = settings.BETA_FEATURES

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
    response["Content-Disposition"] = (
        f'attachment; filename="{config.display_name}.json"'
    )
    return response


@login_required
def configuration_yaml(request, config_id=None):
    config = Configuration.get_or_none(config_id)
    if config is None:
        raise Http404(_("Configuration not found"))

    if config.organization != request.user.profile.organization:
        raise PermissionDenied()

    return HttpResponse(config.builder.render(), content_type="text/yaml")


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
        logger.error(f"Unable to delete configuration {config.id}: {exp}")
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
        logger.error(f"Unable to duplicate configuration {config.id}: {exp}")
        messages.error(
            request,
            _("Unable to duplicate Configuration <em>%(config)s</em>: -- ref %(err)s")
            % {"config": config, "err": exp},
        )

    return redirect("configuration_list")
