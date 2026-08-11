# blog/views.py
from django.views.generic import DetailView, ListView

from .models import Post


class BlogListView(ListView):
    model = Post
    template_name = "blog.html"
    queryset = Post.published.all()
    context_object_name = "post_list"
    paginate_by = 5


class BlogTagView(BlogListView):
    """Posts filtered by a tag, e.g. /blog/tag/transcript/."""

    def get_queryset(self):
        return super().get_queryset().filter(tags__name__iexact=self.kwargs["tag"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tag"] = self.kwargs["tag"]
        return context


class BlogDetailView(DetailView):
    model = Post
    template_name = "post_detail.html"
    queryset = Post.published.all()
