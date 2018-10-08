#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import json

from django.db import models
from django.conf import settings
from django.contrib.auth.models import User

from manager.pibox.util import ONE_GB


class Organization(models.Model):
    slug = models.SlugField(primary_key=True)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    units = models.IntegerField()

    @classmethod
    def create_kiwix(cls):
        if cls.objects.filter(slug="kiwix").count():
            return cls.objects.get(slug="kiwix")
        return cls.objects.create(
            slug="kiwix", name="Kiwix", email="reg@kiwix.org", units=100000
        )

    def __str__(self):
        return self.name


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    @classmethod
    def create_admin(cls):
        organization = Organization.create_kiwix()

        if User.objects.filter(username="admin").count():
            user = User.objects.get(username="admin")
        else:
            user = User.objects.create_superuser(
                username="admin",
                email=organization.email,
                password=settings.ADMIN_PASSWORD,
            )
        if cls.objects.filter(user=user).count():
            return cls.objects.get(user=user)

        return cls.objects.create(user=user, organization=organization)

    def __str__(self):
        return "{user} ({org})".format(user=str(self.user), org=str(self.organization))


class Address(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    recipient = models.CharField(max_length=100)
    phone = models.CharField(max_length=30)
    address = models.TextField()

    def __str__(self):
        return self.name


class Media(models.Model):
    class Meta:
        unique_together = (("kind", "size"),)

    name = models.CharField(max_length=50)
    kind = models.CharField(max_length=50)
    size = models.IntegerField()
    units_coef = models.FloatField()

    @classmethod
    def get_min_for(cls, size):
        try:
            return cls.objects.filter(size__gte=size // ONE_GB).order_by("size").first()
        except cls.DoesNotExist:
            return None

    def __str__(self):
        return self.name

    @property
    def bytes(self):
        return self.size * ONE_GB

    @property
    def units(self):
        return self.size * self.units_coef


class Configuration(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    config = models.TextField(default="{}")
    updated_on = models.DateTimeField(auto_now=True)

    @classmethod
    def get_or_none(cls, id):
        try:
            return cls.objects.get(id=id)
        except cls.DoesNotExist:
            return None

    @property
    def json_config(self):
        return json.loads(self.config)

    @property
    def min_media(self):
        return Media.objects.all()[0]

    @property
    def min_units(self):
        return self.min_media.units

    def __str__(self):
        return self.name


class Order(models.Model):
    CREATED = "created"
    PENDING = "pending"
    COMPLETED = "completed"

    STATUSES = {CREATED: "Created", PENDING: "Pending", COMPLETED: "Completed"}

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    address = models.ForeignKey(Address, on_delete=models.PROTECT)

    created_on = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=STATUSES.items())

    def __str__(self):
        return "Order #{id}".format(self.id)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    configuration = models.ForeignKey(Configuration, on_delete=models.PROTECT)
    media = models.ForeignKey(Media, on_delete=models.PROTECT)
    quantity = models.IntegerField()

    def __str__(self):
        return "OrderItem #{id} (Order #{order})".format(
            id=self.id, order=self.order.id
        )

    @property
    def units(self):
        return self.media.units * self.quantity
