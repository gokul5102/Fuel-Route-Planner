"""Settings for the test suite.

Tests must run on a fresh clone with no `.env`, so a throwaway SECRET_KEY is
supplied here (never used outside tests). Everything else comes from the
normal settings module.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-only-not-secret")

from fuelroute.settings import *  # noqa: E402, F403

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
