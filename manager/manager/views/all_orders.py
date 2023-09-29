#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 nu

import logging

from ansi2html import Ansi2HTMLConverter
from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from manager.decorators import staff_required
from manager.models import Order, OrderData
from manager.scheduler import (
    delete_order,
    get_order,
    test_connection,
)
from manager.views.common import APIQuerySet

logger = logging.getLogger(__name__)


class OrdersQuerySet(APIQuerySet):
    def process(self, results):
        return [OrderData(order) for order in super().process(results)]


@staff_required
def get_list(request):
    success, code, msg = test_connection()
    if not success:
        messages.error(
            request,
            _("Unable to connect (HTTP %(code)s) to API at <code>%(url)s</code>%(msg)s")
            % {
                "url": settings.CARDSHOP_API_URL,
                "code": code,
                "msg": f" -- {msg if msg else ''}",
            },
        )
        return redirect("admin")

    items = OrdersQuerySet("/orders/")
    page = request.GET.get("page")
    paginator = Paginator(items, 10)
    orders_page = paginator.get_page(page)

    context = {
        "orders_page": orders_page,
        "orders": orders_page.object_list,
    }

    if success:
        messages.set_level(request, messages.DEBUG)
        messages.debug(
            request,
            _("Connected to Scheduler API at <code>%(url)s</code>")
            % {"url": settings.CARDSHOP_API_URL},
        )

    return render(request, "all_orders.html", context)


@staff_required
def delete(request, order_id):
    success, res = delete_order(order_id)
    if not success:
        logger.error(f"Unable to delete order: {res}")
        messages.error(
            request,
            _("Unable to delete order %(order_id)s: -- ref: %(err)s")
            % {"order_id": order_id, "err": res},
        )
    else:
        messages.success(
            request,
            _("Successfuly deleted order: %(order_id)s") % {"order_id": order_id},
        )

    return redirect("all-orders")


@staff_required
def recreate(request, order_id):
    order = Order.get_by_scheduler_id(order_id)
    if order is None:
        raise Http404(
            _("Order `%(order_id)s` does not exists") % {"order_id": order_id}
        )
    try:
        new_order = order.recreate()
    except Exception as exc:
        logger.error(f"Unable to recreate order: {exc}")
        logger.exception(exc)
        messages.error(
            request,
            _("Unable to recreate order %(order_id)s: -- ref: %(err)s")
            % {"order_id": order_id, "err": exc},
        )
    else:
        messages.success(
            request,
            _("Successfuly recreated order: %(new_id)s (NEW)")
            % {"new_id": new_order.scheduler_id},
        )

    return redirect("all-orders")


@staff_required
def detail(request, order_id):
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

    retrieved, order = get_order(order_id)
    context = {"orderdata": OrderData(order)}

    if success:
        messages.set_level(request, messages.DEBUG)
        messages.debug(
            request,
            _("Connected to Scheduler API at <code>%(url)s</code>")
            % {"url": settings.CARDSHOP_API_URL},
        )
    return render(request, "all_orders-detail.html", context)


@staff_required
def order_log(request, order_id, step, kind, index=None, fmt="txt"):  # noqa: ARG001
    if fmt not in ("txt", "html"):
        raise Http404(_("Unhandled format `%(fmt)s`") % {"fmt": fmt})
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
        raise Http404(_("`%(kind)s` log does not exists") % {"kind": kind})

    retrieved, order = get_order(order_id, with_logs=True)
    if not retrieved:
        raise Http404(order)

    try:
        if step == "write":
            index = int(index) - 1
            content = order["tasks"][step][index]["logs"][kind]
        else:
            content = order["tasks"][step]["logs"][kind]
    except Exception as exc:
        logger.exception(exc)
        raise Http404(
            _("Log %(step)s/%(kind)s.txt does not exists for Order #%(id)s")
            % {"step": step, "kind": kind, "id": order_id}
        ) from exc

    if content and fmt == "html":
        try:
            content = Ansi2HTMLConverter().convert(content)
        except Exception as exc:
            logger.error("Unable to convert content to HTML")
            logger.exception(exc)

    return HttpResponse(content, content_type=mime)
