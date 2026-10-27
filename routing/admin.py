from django.contrib import admin

from routing.models import Station


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ["opis_id", "name", "city", "state", "price_per_gallon", "geocode_source"]
    # "=state" matches the state exactly, so "WI" finds Wisconsin, not "KWIK TRIP".
    search_fields = ["name", "city", "=state"]
    list_filter = ["state", "geocode_source"]
    list_per_page = 50
