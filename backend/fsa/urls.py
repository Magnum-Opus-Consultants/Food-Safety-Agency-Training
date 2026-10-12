from django.contrib import admin
from django.urls import path

from fsa.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/fsa/", api.urls),
]
