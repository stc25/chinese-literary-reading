from django.urls import include, path
from social_django import views as social_views

from . import views

urlpatterns = [
    path("login", views.login, name="auth.login"),
    path("logout", views.logout_view, name="auth.logout"),
    path("signin-error", views.signin_error, name="auth.signin_error"),
    path("reviewer-mode", views.toggle_reviewer_mode, name="auth.toggle_reviewer_mode"),
    # The completion URL registered in Entra; `auth.callback` names it.
    path(f"auth/sso/complete/{views.BACKEND}/", social_views.complete, {"backend": views.BACKEND},
         name="auth.callback"),
    path("auth/sso/", include("social_django.urls", namespace="social")),
]
