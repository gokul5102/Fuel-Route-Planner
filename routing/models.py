from django.db import models


class Station(models.Model):
    """A truck stop from the fuel price file: one per OPIS ID, at its cheapest price.

    Coordinates are city-level (the file only has highway-exit addresses).
    """

    class GeocodeSource(models.TextChoices):
        CENSUS = "census", "Census Gazetteer"
        NOMINATIM = "nominatim", "Nominatim"

    opis_id = models.IntegerField("OPIS ID", primary_key=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    price_per_gallon = models.DecimalField(max_digits=10, decimal_places=8)
    lat = models.FloatField()
    lon = models.FloatField()
    geocode_source = models.CharField(max_length=20, choices=GeocodeSource.choices)

    class Meta:
        ordering = ["opis_id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state})"
