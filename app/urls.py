from django.http import Http404, JsonResponse
from django.urls import path

from . import views

handler404 = "app.views.not_found"


def health(request):
    return JsonResponse({"status": "ok"})


def not_yet(request, *args, **kwargs):
    raise Http404   # placeholder for a page a later task ports (Task 5 assistant, Task 6 sign-in)


urlpatterns = [
    path("healthz", health, name="health"),
    path("", views.course_map, name="pages.course_map"),
    path("welcome", views.welcome, name="pages.welcome"),
    path("units/<str:uid>", views.unit, name="pages.unit"),
    path("units/<str:uid>/<str:num>", views.passage, name="pages.passage"),
    path("grammar", views.grammar_index, name="pages.grammar_index"),
    path("grammar/<str:gid>", views.grammar, name="pages.grammar"),
    path("summaries.json", views.summaries, name="pages.summaries"),
    path("toolkit", views.toolkit_index, name="pages.toolkit_index"),
    path("toolkit/<str:tid>", views.toolkit, name="pages.toolkit"),
    path("glossary", views.glossary, name="pages.glossary"),
    path("review", views.review_list, name="pages.review_list"),
    path("accessibility", views.accessibility, name="pages.accessibility"),
    # Placeholders so the shared templates can link to them; Tasks 5 and 6 replace them.
    path("login", not_yet, name="auth.login"),
    path("logout", not_yet, name="auth.logout"),
    path("reviewer-mode", not_yet, name="auth.toggle_reviewer_mode"),
    path("assistant/", not_yet, name="assistant.page"),
    path("assistant/help", not_yet, name="assistant.help"),
]
