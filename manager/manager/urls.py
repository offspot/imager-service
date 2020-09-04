#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from django.urls import path
from django.contrib import admin as django_admin
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static

from manager.views import ui
from manager.views import api
from manager.views import admin
from manager.views import config
from manager.views import scheduler
from manager.views import all_orders

urlpatterns = (
    [
        # API
        path(
            "api/packages/lang_<lang_code>",
            api.packages_for_language,
            name="api_packages_for_language",
        ),
        path("api/get_size", api.required_size_for_config, name="api_get_size"),
        path(
            "api/medias_choices/<int:config_id>",
            api.media_choices_for_configuration,
            name="api_medias_choices",
        ),
        # configuration
        path("configurations/new", config.configuration_edit, name="configuration_add"),
        path(
            "configurations/<int:config_id>/delete",
            config.configuration_delete,
            name="configuration_delete",
        ),
        path(
            "configurations/<int:config_id>/duplicate",
            config.configuration_duplicate,
            name="configuration_duplicate",
        ),
        path(
            "configurations/<int:config_id>",
            config.configuration_edit,
            name="configuration_edit",
        ),
        path(
            "configurations/<int:config_id>.json",
            config.configuration_export,
            name="configuration_export",
        ),
        path("configurations/", config.configuration_list, name="configuration_list"),
        # addresses
        path(
            "addresses/<int:address_id>/delete",
            ui.address_delete,
            name="address_delete",
        ),
        path("addresses/<int:address_id>", ui.address_edit, name="address_edit"),
        path("addresses/new", ui.address_edit, name="address_new"),
        path("addresses/", ui.address_list, name="address_list"),
        # orders (ful)
        path(
            "orders/f/<str:order_id>",
            ui.order_detail_scheduler_id,
            name="order_detail_scheduler_id",
        ),
        path(
            "orders/f/<str:order_id>/add_shipping",
            ui.order_add_shipping,
            name="order_add_shipping",
        ),
        # orders
        path("orders/new", ui.order_new, name="order_new"),
        path("orders/<str:order_min_id>/cancel", ui.order_cancel, name="order_cancel"),
        path("orders/<str:order_min_id>", ui.order_detail, name="order_detail"),
        path("orders/", ui.order_list, name="order_list"),
        # all orders
        path(
            "all-orders/<str:order_id>/logs/<str:step>/<str:kind>-<int:index>.<str:fmt>",
            all_orders.order_log,
            name="order_log",
        ),
        path(
            "all-orders/<str:order_id>/logs/<str:step>/<str:kind>.<str:fmt>",
            all_orders.order_log,
            name="order_log",
        ),
        path(
            "all-orders/<str:order_id>/delete",
            all_orders.delete,
            name="all-orders-delete",
        ),
        path("all-orders/<str:order_id>", all_orders.detail, name="all-orders-detail"),
        path("all-orders/", all_orders.list, name="all-orders"),
        # manager admin
        path(
            "admin/toggle_account/<str:username>",
            admin.toggle_account,
            name="admin_toggle_account",
        ),
        path(
            "admin/delete_account/<str:username>",
            admin.delete_account,
            name="admin_delete_account",
        ),
        path("admin/", admin.dashboard, name="admin"),
        # scheduler
        path(
            "scheduler/disable_warehouse/<str:warehouse_id>",
            scheduler.warehouse_disable,
            name="scheduler_disable_warehouse",
        ),
        path(
            "scheduler/enable_warehouse/<str:warehouse_id>",
            scheduler.warehouse_enable,
            name="scheduler_enable_warehouse",
        ),
        path(
            "scheduler/disable_channel/<str:channel_id>",
            scheduler.channel_disable,
            name="scheduler_disable_channel",
        ),
        path(
            "scheduler/enable_channel/<str:channel_id>",
            scheduler.channel_enable,
            name="scheduler_enable_channel",
        ),
        path(
            "scheduler/disable_user/<str:user_id>",
            scheduler.user_disable,
            name="scheduler_disable_user",
        ),
        path(
            "scheduler/enable_user/<str:user_id>",
            scheduler.user_enable,
            name="scheduler_enable_user",
        ),
        path("scheduler/refresh", scheduler.refresh_token, name="scheduler-refresh"),
        path("scheduler/", scheduler.dashboard, name="scheduler"),
        # basics
        path("django-admin/", django_admin.site.urls),
        path(
            "login/",
            auth_views.LoginView.as_view(template_name="login.html"),
            name="login",
        ),
        path("logout/", auth_views.LogoutView.as_view(), name="logout"),
        path("password", ui.password_change, name="change_password"),
        path("delete", ui.delete_account, name="delete_account"),
        path("", ui.home, name="home"),
    ]
    + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
)
