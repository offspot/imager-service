#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import json
import base64
import tempfile

import pytz
import magic

from django import forms
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt, csrf_protect

from manager.models import Configuration
from manager.pibox import (ideascube_languages, b64decode, get_packages_id,
                           PACKAGES_BY_LANG, PACKAGES_LANGS, ALL_PACKAGES)


class JSONUploadForm(forms.Form):
    # name = forms.CharField(max_length=50)
    file = forms.FileField(
        widget=forms.FileInput(
            attrs={'class' : 'form-control form-check-input'}))


def handle_uploaded_json(fd):
    try:
        payload = fd.read()
        if type(payload) is bytes:
            payload = payload.decode("UTF-8")
        jsdata = json.loads(payload)
    except Exception:
        raise
        return None

    config = {}

    def set_if_string(data, default=None):
        if isinstance(data, str):
            return data
        return default

    def set_if_string_in(data, values, default=None):
        if isinstance(data, str) and data in values:
            return data
        return default

    def set_if_list_within(data, values, default=[]):
        if not isinstance(data, list):
            return default
        return [item for item in data if item in values]

    def get(keys):
        if isinstance(keys, str):
            keys = [keys]
        try:
            assert len(keys)
            val = jsdata
            for key in keys:
                val = val[key]
        except Exception:
            val = None
        return val

    languages = ['fr', 'en']
    timezones = ['UTC', 'Africa/Bamako', 'Europe/Paris', 'Europe/Berlin']
    catalog_ids = get_packages_id()

    # wifi
    wifi_password = set_if_string(get(['wifi', 'password']), "piboxwifipwd")
    wifi_protected = bool(get(['wifi', 'protected']))

    # admin account
    admin_password = set_if_string(get(['admin_account', 'password']), "admin")
    admin_login = set_if_string(get(['admin_account', 'login']), "admin")
    admin_custom = bool(get(['admin_account', 'custom']))

    # contents
    aflatoun = bool(get(['content', 'aflatoun']))
    edupi = bool(get(['content', 'edupi']))
    edupi_resources = set_if_string(get(['content', 'edupi_resources']), None)
    packages_list = set_if_list_within(get(['content', 'zims']), catalog_ids)
    wikifundi = set_if_list_within(get(['content', 'wikifundi']), ['fr', 'en'])
    kalite = set_if_list_within(get(['content', 'kalite']), ['fr', 'en', 'es'])

    def test_file(fname, data, mimes):
        fpath = b64decode(fname, data, tempfile.mkdtemp())
        mime = magic.Magic(mime=True)
        return mime.from_file(fpath) in mimes

    # branding
    def get_branding(key, mimes):
        fname = os.path.basename(
            set_if_string(get(['branding', key, 'fname']), "styles.css"))
        data = set_if_string(get(['branding', key, 'data']), "-")
        if test_file(fname, data, mimes):
            return {'fname': fname, 'data': data}
        return None

    # rebuild clean config from data
    config = {
        "project_name": set_if_string(get('project_name')),
        "language": set_if_string_in(get('language'), languages, "en"),
        "timezone": set_if_string_in(get('timezone'), timezones, "UTC"),
        "wifi": {
            "password": wifi_password,
            "protected": wifi_protected,
        },
        "admin_account": {
            "password": admin_password,
            "login": admin_login,
            "custom": admin_custom,
        },
        "content": {
            "aflatoun": aflatoun,
            "wikifundi": wikifundi,
            "zims": packages_list,
            "kalite": kalite,
            "edupi": edupi,
            "edupi_resources": edupi_resources,
        },
        "branding": {
            "css": get_branding('css', ['text/css', 'text/plain']),
            "logo": get_branding('logo', ['image/png']),
            "favicon": get_branding('favicon', ['image/x-icon', 'image/png']),
        }
    }

    return config


@login_required
def home(request):
    return render(request, 'home.html', {})

@login_required
def configurations(request):

    context = {}
    context['configurations'] = Configuration.objects.filter(
        organization=request.user.profile.organization)

    if request.method == 'POST':
        print("POST")
        form = JSONUploadForm(request.POST, request.FILES)
        if form.is_valid():
            print("valid form")
            js_config = handle_uploaded_json(request.FILES['file'])
            # from pprint import pprint as pp ; pp(js_config)
            config = Configuration.objects.create(
                organization=request.user.profile.organization,
                name=js_config.get("project_name", "Imported config"),
                config=json.dumps(js_config)
                )
            return redirect('edit_configuration', config.id)
        else:
            print("not valid")
            # from pprint import pprint as pp ; pp(form.errors)
    else:
        print("GET")
        form = JSONUploadForm()

    context['form'] = form

    return render(request, 'configurations.html', context)


@login_required
def configuration(request, config_id=None):
    context = {}

    if config_id is not None:
        config = Configuration.get_or_none(config_id)
        assert config.organization == request.user.profile.organization
        context['config'] = config.json_config
    else:
        context['config'] = {}

    # language
    context['languages'] = ideascube_languages
    context['timezones'] = pytz.common_timezones
    context['packages_langs'] = PACKAGES_LANGS
    context['packages'] = [PACKAGES_BY_LANG[pid.rsplit('.', 1)[-1]].get(pid)
                           for pid in context['config'].get('content', {})
                           .get('zims', [])]
    # from pprint import pprint as pp ; pp(context)
    return render(request, 'edit_configuration.html', context)


@login_required
def orders(request):
    return render(request, 'home.html', {})

@login_required
def organizations(request):
    return render(request, 'home.html', {})

@login_required
def tokens(request):
    return render(request, 'home.html', {})
