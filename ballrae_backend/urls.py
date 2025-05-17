from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path('api/users/', include('ballrae_backend.users.urls')), 
    path('api/teams/', include('ballrae_backend.teams.urls')),
]
