"""Project URL configuration — DRF router with nested resource routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProjectResourceViewSet, ProjectViewSet

app_name = "projects"


class NoTrailingSlashRouter(DefaultRouter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trailing_slash = ""


router = NoTrailingSlashRouter()
router.register("projects", ProjectViewSet, basename="project")

project_collection_slash = ProjectViewSet.as_view({"get": "list", "post": "create"})

resource_list = ProjectResourceViewSet.as_view({"get": "list", "post": "create"})
resource_detail = ProjectResourceViewSet.as_view({"delete": "destroy"})

urlpatterns = [
    path("projects/", project_collection_slash, name="project-list-slash"),
    path("", include(router.urls)),
    path(
        "projects/<uuid:project_id>/resources",
        resource_list,
        name="project-resource-list",
    ),
    path(
        "projects/<uuid:project_id>/resources/<uuid:resource_id>",
        resource_detail,
        name="project-resource-detail",
    ),
]
