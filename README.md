# Overview

Cardshop is a solution for semi-automation of SD-cards creation using a central scheduler, creator workers (to create image files), downloader workers and writer workers (to write images onto real SD-cards).

Contact kelson@kiwix.org regarding actual deployment.

Architecture is based on [zimfarm](https://github.com/openzim/zimfarm)'s

## Warehouse

`warehouse`: A container on a machine with plenty of space (must be able to receive images created by all _creators_ and retain them until downloaded by _downloaders_). It is an FTP server which authenticates through the scheduler.

## Creator

`creator`: A container fetching Tasks from scheduler, creating images and uploading them to the warehouse.

Must be on a powerful computer with lots of space (300G to build 256G images).

## Downloader

`downloader`: A container downloading images from the warehouse so it can be written by a `writer` worker (shares credentials with writer – must be on same computer).

## Writer

`writer`: A container writing images to SD-cards. Image files must be present (downloaded by the `downloader` worker).

## Writer Host (whost)

A non-docker tool installed on the Writers' host to configure and manage the workers:

* SD-slots identification
* Configuration for:
 - network
 - authentication
 - SD-card writers (USB device to Name association)
* Auto start of `downloader` and `writer` containers.

Must be physically accessible, CPU doesn't matter, large space (256G per worker on host).

## Manager

`manager`: A container providing a UI to create orders and manage users. Technically optional.

## Scheduler

* `mongo` MongoDB container to hold persistent data (`Users`, `Tokens`, `Orders`, `Tasks`, etc.)
* `scheduler`: API providing CRUD for persistent Data and managing Authentication for all services.


# Authentication

* Users all have a `username`+`password` pair.
* Scheduler offers Tokens for `username:password`.
* Manager and workers identifies via Token to work the API.
* Creator and Downloader identifies with Warehouse via a Token obtained from Scheduler.

Tokens are 2 fold:

* Access token, 60mn TTL: needed to work the API.
* Refresh token, 30d TTL: allows one to get new Access Token.
* Credentials authentication returns both at once.
