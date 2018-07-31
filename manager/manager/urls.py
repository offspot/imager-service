#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from django.urls import path
from django.contrib import admin
from django.contrib.auth import views as auth_views

from manager.views import ui
from manager.views import api

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/',
         auth_views.LoginView.as_view(template_name='login.html'),
         name='login'),
    path('logout/',
         auth_views.LogoutView.as_view(),
         name='logout'),

    path('api/packages/lang_<lang_code>',
         api.packages_for_language,
         name='api_packages_for_language'),
    path('api/get_size',
         api.required_size_for_config,
         name='api_get_size'),

    path('configurations/new', ui.configuration, name='add_configuration'),
    path('configurations/<int:config_id>',
         ui.configuration, name='edit_configuration'),
    path('configurations', ui.configurations, name='configurations'),

    path('orders', ui.orders, name='orders'),
    path('organizations', ui.organizations, name='organizations'),
    path('tokens', ui.tokens, name='tokens'),
    path('', ui.home, name='home'),
]
