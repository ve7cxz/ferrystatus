from django.urls import path, re_path
from . import views
urlpatterns = [
    path('about', views.about ),
    path('faq', views.faq ),
    path('privacy', views.privacy ),
    re_path(r'(.*)$', views.home ),
    #re_path(r'^(all-sailings|sailings|sailings/.+)$', views.sailings ),
    #re_path(r'^(routes|routes/.+)$', views.routes ),
    #path('ferries', views.ferries ),
]
