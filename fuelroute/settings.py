"""Django settings for the fuel route planner.

Every deploy-specific value is read from the environment (or a `.env` file in
the project root) through django-environ. See `.env.example` for the full list.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# --- Core -------------------------------------------------------------------

SECRET_KEY = env("SECRET_KEY")  # required: no default, so it is never hardcoded
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "routing",
]

MIDDLEWARE = [
    "routing.middleware.RequestMetricsMiddleware",  # first, so it times everything below
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "fuelroute.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "fuelroute.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

CACHES = {"default": env.cache("CACHE_URL", default="locmemcache://")}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# --- Logging ----------------------------------------------------------------------
# The app's own loggers print to the console; "routing.requests" writes one line per
# request with its external calls and per-stage timings.

LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"routing": {"handlers": ["console"], "level": LOG_LEVEL}},
}

# --- API docs ---------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "routing.errors.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Fuel Route Planner API",
    "DESCRIPTION": "Plans the cheapest fuel stops for a road trip between two places in the USA.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",  # the default
        "routing.api_docs.add_map_page",  # the map page is a plain Django view
    ],
}

# --- External services --------------------------------------------------------

OSRM_BASE_URL = env("OSRM_BASE_URL", default="https://router.project-osrm.org")
NOMINATIM_BASE_URL = env("NOMINATIM_BASE_URL", default="https://nominatim.openstreetmap.org")
NOMINATIM_USER_AGENT = env(
    "NOMINATIM_USER_AGENT", default="fuel-route-planner/0.1 (take-home assessment)"
)
HTTP_TIMEOUT_SECONDS = env.float("HTTP_TIMEOUT_SECONDS", default=10)

# --- Vehicle and Corridor -------------------------------------------------------

CORRIDOR_MILES = env.float("CORRIDOR_MILES", default=8)
RANGE_MILES = env.float("RANGE_MILES", default=500)
MPG = env.float("MPG", default=10)
MIN_RESERVE_MILES = env.float("MIN_RESERVE_MILES", default=0)

# --- Cache lifetimes ------------------------------------------------------------

PLAN_CACHE_SECONDS = env.int("PLAN_CACHE_SECONDS", default=24 * 60 * 60)
GEOCODE_CACHE_SECONDS = env.int("GEOCODE_CACHE_SECONDS", default=30 * 24 * 60 * 60)

# --- Data files (committed, except the raw download cache) -----------------------

DATA_DIR = BASE_DIR / "data"
PRICE_FILE = DATA_DIR / "fuel-prices-for-be-assessment.csv"
US_PLACES_FILE = DATA_DIR / "us_places.csv"
CITY_COORDS_FILE = DATA_DIR / "city_coords.csv"
GAZETTEER_CACHE_DIR = DATA_DIR / ".cache"
