from unittest.mock import patch

import pytest
from django.db.utils import OperationalError
from django.urls import reverse


@pytest.mark.django_db
def test_health_checks_postgresql(client):
    response = client.get(reverse("health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_reports_unavailable_database(client):
    with patch("apps.core.views.connection.cursor", side_effect=OperationalError):
        response = client.get(reverse("health"))
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


@pytest.mark.django_db
def test_user_persistence():
    from django.contrib.auth import get_user_model
    user = get_user_model().objects.create_user(username="tester", password="test-password")
    user.refresh_from_db()
    assert user.check_password("test-password")
