#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import json
import collections

from django.db.models import Max
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from manager.models import Media, Configuration
from manager.pibox.packages import PACKAGES_BY_LANG
from manager.pibox.util import human_readable_size, ONE_GB
from manager.pibox.content import get_collection, get_required_image_size


def packages_for_language(request, lang_code):
    if request.GET.get("order") == "size":
        order = ("size", True)
    else:
        order = ("sname", False)

    def _filter(package):
        return {
            k: v
            for k, v in package.items()
            if k
            in (
                "sname",
                "hsize",
                "tags",
                "version",
                "type",
                "description",
                "size",
                "skey",
                "key",
            )
        }

    ordered = collections.OrderedDict(
        sorted(
            [(k, _filter(v)) for k, v in PACKAGES_BY_LANG.get(lang_code, {}).items()],
            key=lambda x: x[1][order[0]],
            reverse=order[1],
        )
    )

    return JsonResponse({"packages": ordered})


@csrf_exempt
@require_POST
def required_size_for_config(request):
    try:
        payload = request.body
        if type(payload) is bytes:
            payload = payload.decode("UTF-8")
        data = json.loads(payload)
    except Exception:
        return JsonResponse({"error": str(request.body)})

    # check disk space
    collection = get_collection(
        edupi=data.get("edupi", False),
        edupi_resources=data.get("edupi_resources", None),
        packages=data.get("packages", []),
        kalite_languages=data.get("kalite", []),
        wikifundi_languages=data.get("wikifundi", []),
        aflatoun_languages=["fr", "en"] if data.get("aflatoun", False) else [],
    )
    required_image_size = get_required_image_size(collection)
    media = Media.get_min_for(required_image_size)
    return JsonResponse(
        {
            "size": required_image_size,
            "hsize": human_readable_size(required_image_size, False),
            "media_size": human_readable_size(media.size * ONE_GB, False)
            if media
            else None,
            "hfree": human_readable_size(media.bytes - required_image_size)
            if media
            else None,
        }
    )


def media_choices_for_configuration(request, config_id):
    all_medias = Media.objects.all()

    config = Configuration.get_or_none(config_id)
    if config is not None and config.organization == request.user.profile.organization:
        medias = [m for m in all_medias if m.bytes >= config.size]
    if not len(medias):
        medias = all_medias.filter(size=all_medias.aggregate(Max("size"))["size__max"])
    return JsonResponse(Media.choices_for(medias), safe=False)
