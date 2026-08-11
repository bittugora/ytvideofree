# blog/urls.py
from django.urls import path

from .feeds import LatestPostsFeed
from .views import BlogDetailView, BlogListView, BlogTagView

urlpatterns = [
    path("", BlogListView.as_view(), name="blog"),
    path("feed/", LatestPostsFeed(), name="blog_feed"),
    path("tag/<str:tag>/", BlogTagView.as_view(), name="blog_tag"),
    path("post/<slug>/", BlogDetailView.as_view(), name="post_detail"),
]
