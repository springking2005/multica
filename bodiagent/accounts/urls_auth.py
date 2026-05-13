"""Public auth API routes."""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

app_name = "accounts_auth"

urlpatterns = [
    path("register", views.register, name="register"),
    path("login", views.login, name="login"),
    path("logout", views.logout, name="logout"),
    path("send-code", views.send_code, name="send-code"),
    path("verify-code", views.verify_code, name="verify-code"),
    path("token-refresh", TokenRefreshView.as_view(), name="token-refresh"),
]
