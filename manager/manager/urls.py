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

urlpatterns = (
    [
        path("django-admin/", django_admin.site.urls),
        path(
            "login/",
            auth_views.LoginView.as_view(template_name="login.html"),
            name="login",
        ),
        path("logout/", auth_views.LogoutView.as_view(), name="logout"),
        path(
            "api/packages/lang_<lang_code>",
            api.packages_for_language,
            name="api_packages_for_language",
        ),
        path("api/get_size", api.required_size_for_config, name="api_get_size"),
        path("configurations/new", config.edit_configuration, name="add_configuration"),
        path(
            "configurations/<int:config_id>",
            config.edit_configuration,
            name="edit_configuration",
        ),
        path(
            "configurations/<int:config_id>.json",
            config.export_configuration,
            name="export_configuration",
        ),
        path("configurations/", config.list_configurations, name="configurations"),
        path("orders/", ui.orders, name="orders"),
        path("admin/toggle_account/<str:username>", admin.toggle_account, name="admin_toggle_account"),
        path("admin/", admin.dashboard, name="admin"),
        path("scheduler/disable_channel/<str:channel_id>", scheduler.channel_disable, name="scheduler_disable_channel"),
        path("scheduler/enable_channel/<str:channel_id>", scheduler.channel_enable, name="scheduler_enable_channel"),
        path("scheduler/disable_user/<str:user_id>", scheduler.user_disable, name="scheduler_disable_user"),
        path("scheduler/enable_user/<str:user_id>", scheduler.user_enable, name="scheduler_enable_user"),
        path("scheduler/", scheduler.dashboard, name="scheduler"),
        path("", ui.home, name="home"),
    ]
    + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
)
