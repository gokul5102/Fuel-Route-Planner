from django.conf import settings


def test_domain_settings_default_to_the_spec_values():
    assert settings.CORRIDOR_MILES == 8
    assert settings.RANGE_MILES == 500
    assert settings.MPG == 10
    assert settings.MIN_RESERVE_MILES == 0
    assert settings.HTTP_TIMEOUT_SECONDS == 10


def test_cache_lifetimes_default_to_one_day_for_plans_and_thirty_days_for_geocodes():
    assert settings.PLAN_CACHE_SECONDS == 24 * 60 * 60
    assert settings.GEOCODE_CACHE_SECONDS == 30 * 24 * 60 * 60


def test_external_service_urls_are_configured():
    assert settings.OSRM_BASE_URL.startswith("https://")
    assert settings.NOMINATIM_BASE_URL.startswith("https://")
    assert settings.NOMINATIM_USER_AGENT


def test_request_log_lines_are_shown_at_info_by_default():
    assert settings.LOG_LEVEL == "INFO"
    assert settings.LOGGING["loggers"]["routing"]["level"] == "INFO"
