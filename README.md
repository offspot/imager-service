# Overview

Cardshop is a solution for semi-automation of SD-cards creation using a central scheduler, creator workers (to create image files) and writer workers (to write images onto real SD-cards).

Contact kelson@kiwix.org regarding actual deployment.

Architecture is based on [zimfarm](https://github.com/openzim/zimfarm)'s

## Warehouse

`warehouse`: A single container on a machine with plenty of space (must be able to receive images created by all _creators_ and retain them until downloaded by _writers_). It is an FTP server which authenticates through the scheduler.

## Creator

`creator`: A single container fetching Tasks from scheduler, creating images and uploading them to the warehouse.

Must be on a powerful computer with lots of space (300G to build 256G images).

## Writer

`writer`: A single container fetching Tasks from scheduler, downloading images, writing them to SD-cards.

Must be physically accessible, no much power required, large space (256G per worker on host).

## Writer-helper

A non-docker tool installed on the Writers' host to configure the workers:

* SD-slot identification
* Configuration file for:
 - network
 - numbers and authentication of writers.
* Auto start of `writer` containers.

## Manager

`manager`: A single container providing a UI to take orders and manage users.

## Scheduler

* `rabbit`: RabbitMQ container to hold the messaging queue between workers and the scheduler.
* `mongo` MongoDB container to hold persistent data (`Users`, `Tokens`, `Orders`, `Tasks`)
* `monitor`: receives all events and passes them through a handler. Updates DB based on workers-emitted events.
* `beat`: Executes periodic tasks and synchronizes Schedules (crontab-like entries of tasks) between the Database and Celery.
* `scheduler`: API providing CRUD for persistent Data and managing Authentication for all services.


# Authentication

* Users all have a `username`+`password` pair.
* Scheduler offers Tokens for `username:password`.
* Manager identifies via Token to work the API.
* Workers identify to RabbitMQ using their credentials over AMQPS. They don't communicate with the API but emits Celery messages (captured by monitor).
* Creator identifies with Warehouse via a Token obtained from Scheduler.

Tokens are 2 fold:

* Access token, 60mn TTL: needed to work the API.
* Refresh token, 30d TTL: allows one to get new Access Token.
* Credentials authentication returns both at once.
