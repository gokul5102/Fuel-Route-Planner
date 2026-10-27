from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from routing.views import PlaceSuggestionsView, RouteView, route_map

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/route/", RouteView.as_view(), name="route"),
    path("api/route/map/", route_map, name="route-map"),
    path("api/places/", PlaceSuggestionsView.as_view(), name="places"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
