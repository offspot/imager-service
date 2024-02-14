import copy
import datetime
import logging
import statistics

from django.core.management.base import BaseCommand
from humanfriendly import format_size, format_timespan

from manager.models import Order

logger = logging.getLogger(__name__)
ONE_GIB = 2**30


class Command(BaseCommand):
    help = "Get info about durations for orders"

    def handle(self, *args, **options):  # noqa: ARG002

        times = {"pending": [], "building": [], "uploading": [], "total": []}
        gib_times = copy.deepcopy(times)
        gib_times["speed"] = []
        ratios = copy.deepcopy(times)

        only_imager = False

        qs = Order.objects.filter(status="completed").exclude(scheduler_data__exact="")
        if only_imager:
            qs = qs.exclude(config_yaml__exact="")

        self.stdout.write(f"looping through {qs.count()} successful orders")

        for order in qs:
            if "tasks" not in order.scheduler_data:
                continue

            self.stdout.write(f"Order #{order.id}")

            try:
                statuses = {
                    item["status"]: datetime.datetime.fromisoformat(item["on"])
                    for item in order.scheduler_data["tasks"]["create"]["statuses"]
                }

                time = {
                    "pending": statuses["received"] - statuses["pending"],
                    "building": statuses["built"] - statuses["building"],
                    "uploading": statuses["uploaded_public"] - statuses["uploading"],
                    "total": statuses["uploaded_public"] - statuses["pending"],
                }
                gib = (
                    order.scheduler_data["tasks"]["create"]["image"]["size"] // ONE_GIB
                )
                if gib < 1:
                    continue
            except KeyError as exc:
                self.stdout.write(self.style.ERROR(f"Order #{order.id}: {exc}"))
                continue

            for status, value in time.items():
                self.stdout.write(f" > {status}: {format_timespan(value)}")
                times[status].append(value.total_seconds())

            for status in times.keys():
                gib_times[status].append(time[status].total_seconds() / gib)
                if status == "uploading":
                    nb_seconds = statistics.median(gib_times[status])
                    bytes_per_second = ONE_GIB // nb_seconds
                    gib_times["speed"].append(bytes_per_second)
                ratios[status].append(
                    time[status].total_seconds() / time["total"].total_seconds()
                )

        self.stdout.write(f"Stats over {len(times['total'])} orders:")
        self.stdout.write("Status,min,max,avg,median")
        for status, values in times.items():
            self.stdout.write(
                f"{status},{min(values)},{max(values)},{statistics.mean(values)},{statistics.median(values)}"
            )

        self.stdout.write("---")

        self.stdout.write("Status\tmin\tmax\tavg\tmedian\tShare\tmedian-by-GiB\tSpeed")
        for status, values in times.items():
            line = (
                f"{status}"
                + f"\t{format_timespan(min(values))}"
                + f"\t{format_timespan(max(values))}"
                + f"\t{format_timespan(statistics.mean(values))}"
                + f"\t{format_timespan(statistics.median(values))}"
                + f"\t{statistics.median(ratios[status])}"
                + f"\t{format_timespan(statistics.median(gib_times[status]))}"
            )
            if status == "uploading":
                bytes_per_second = statistics.median(gib_times["speed"])
                bits_per_second = bytes_per_second * 8
                byps = format_size(bytes_per_second, binary=True)
                bips = format_size(bits_per_second, binary=False)
                line += f"\t{bips}/s ({byps}/s)"
            self.stdout.write(line)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("done"))
