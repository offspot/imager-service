#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging

from django.http import Http404, HttpResponse
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect
from ansi2html import Ansi2HTMLConverter

from manager.models import OrderData
from manager.decorators import staff_required
from manager.scheduler import (
    test_connection,
    as_items_or_none,
    get_orders_list,
    delete_order,
    get_order,
    get_task,
)

logger = logging.getLogger(__name__)


@staff_required
def list(request):

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

    orders = sorted(
        [OrderData(order) for order in as_items_or_none(*get_orders_list())],
        key=lambda item: item["statuses"][0]["on"],
        reverse=True,
    )
    context = {"orders": orders or None}

    if success:
        messages.set_level(request, messages.DEBUG)
        messages.debug(
            request,
            "Connected to Scheduler API at <code>{url}</code>".format(
                url=settings.CARDSHOP_API_URL
            ),
        )

    return render(request, "all_orders.html", context)


@staff_required
def delete(request, order_id):
    success, res = delete_order(order_id)
    if not success:
        logger.error("Unable to delete order: {}".format(res))
        messages.error(
            request, "Unable to delete order {}: -- ref: {}".format(order_id, res)
        )
    else:
        messages.success(request, "Successfuly deleted order: {}".format(order_id))

    return redirect("all-orders")


@staff_required
def detail(request, order_id):
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

    retrieved, order = get_order(order_id)
    context = {"orderdata": OrderData(order)}

    if success:
        messages.set_level(request, messages.DEBUG)
        messages.debug(
            request,
            "Connected to Scheduler API at <code>{url}</code>".format(
                url=settings.CARDSHOP_API_URL
            ),
        )
    return render(request, "all_orders-detail.html", context)


@staff_required
def order_log(request, order_id, step, kind, index=None, fmt="txt"):
    if fmt not in ("txt", "html"):
        raise Http404("Unhandled format `{}`".format(fmt))
    else:
        mime = {"txt": "text/plain", "html": "text/html"}.get(fmt)

    if step not in ("create", "download", "write") or kind not in (
        "worker",
        "installer",
        "uploader",
        "downloader",
        "wipe",
        "writer",
    ):
        raise Http404("`{}` log does not exists".format(kind))

    retrieved, order = get_order(order_id)
    if not retrieved:
        raise Http404(order)

    try:
        if step == "write":
            index = int(index) - 1
            content = order["tasks"][step][index]["logs"][kind]
        else:
            content = order["tasks"][step]["logs"][kind]
    except Exception as exp:
        logger.exception(exp)
        raise Http404(
            "Log {step}/{kind}.txt does not exists for Order #{id}".format(
                step=step, kind=kind, id=order_id
            )
        )

    if content and fmt == "html":
        try:
            content = Ansi2HTMLConverter().convert(content)
        except Exception as exp:
            logger.error("Unable to convert content to HTML")
            logger.exception(exp)

    return HttpResponse(content, content_type=mime)
