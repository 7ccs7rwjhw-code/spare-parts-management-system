from django.urls import path, include
from django.contrib import admin
from apps.core import views as v

urlpatterns = [
    path("imports/<int:pk>/catalog/", v.catalog_commit, name="catalog_commit"),
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("health/", v.health, name="health"),
    path("", v.home, name="home"),
    path("batches/new/", v.batch_new, name="batch_new"),
    path("batches/<int:pk>/", v.detail, name="detail"),
    path("batches/<int:pk>/line/", v.edit_line, name="line_new"),
    path("batches/<int:pk>/line/<int:lid>/", v.edit_line, name="line_edit"),
    path("batches/<int:pk>/line/<int:lid>/delete/", v.remove_line, name="line_delete"),
    path("batches/<int:pk>/action/<str:act>/", v.action, name="action"),
    path("batches/<int:pk>/copy/", v.copy_batch, name="copy"),
    path(
        "batches/<int:pk>/revision/", v.copy_batch, {"revision": True}, name="revision"
    ),
    path("items/", v.items, name="items"),
    path("items/new/", v.item_edit, name="item_new"),
    path("items/<uuid:pk>/", v.item_edit, name="item_edit"),
    path("items/<uuid:pk>/json/", v.item_json, name="item_json"),
    path("imports/", v.imports, name="imports"),
    path("imports/<int:pk>/", v.import_detail, name="import_detail"),
    path("imports/<int:pk>/csv/", v.issues_csv, name="issues_csv"),
    path("imports/<int:pk>/original/", v.original, name="original"),
    path("reports/", v.reports, name="reports"),
    path("export/", v.export, name="export"),
    path("queue/", v.queue, name="queue"),
    path("queue/<int:pk>/bind/", v.bind, name="bind"),
    path("audit/", v.audit, name="audit"),
]
