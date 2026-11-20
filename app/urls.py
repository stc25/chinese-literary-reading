from django.http import JsonResponse
from django.urls import path
from django.views.generic import RedirectView

from . import views
from .assistant import views as assistant_views

def health(request):
    return JsonResponse({"status": "ok"})


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
    path("assistant", RedirectView.as_view(pattern_name="assistant.page", permanent=False)),
    path("assistant/", assistant_views.page, name="assistant.page"),
    path("assistant/help", assistant_views.help, name="assistant.help"),
    path("assistant/api/<str:step>", assistant_views.api, name="assistant.api"),
]
