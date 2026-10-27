"""Load the fuel price file into the Station table (offline, about a second).

Re-runnable: the table is cleared and refilled in one transaction.
"""

import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from routing.models import Station
from routing.services.stations import clean_stations, read_city_coords, read_price_file


class Command(BaseCommand):
    help = "Load Stations from the fuel price file and the city coordinates file."

    def handle(self, *args, **options):
        started = time.perf_counter()
        cleaned = clean_stations(
            read_price_file(settings.PRICE_FILE),
            read_city_coords(settings.CITY_COORDS_FILE),
        )

        with transaction.atomic():
            Station.objects.all().delete()
            Station.objects.bulk_create(Station(**vars(station)) for station in cleaned.stations)

        elapsed = time.perf_counter() - started
        self.stdout.write(
            f"{cleaned.rows_read} rows read, "
            f"{cleaned.duplicate_rows} exact duplicate(s) dropped, "
            f"{len(cleaned.stations)} Stations loaded, "
            f"{cleaned.skipped_unresolved} skipped (city unresolved) "
            f"in {elapsed:.2f} s"
        )
