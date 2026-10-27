"""
WSGI config for fuelroute project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fuelroute.settings")

application = get_wsgi_application()

from routing.services.places import get_place_index  # noqa: E402
from routing.services.station_index import warm_station_index  # noqa: E402

warm_station_index()  # one query, then every request uses the in-memory index
get_place_index()  # the "City, ST" lookup (~0.1 s from data/us_places.csv)
