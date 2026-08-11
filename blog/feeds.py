from django.contrib.syndication.views import Feed

from .models import Post


class LatestPostsFeed(Feed):
    title = "ytvideofree Blog"
    link = "/blog/"
    description = "Guides and notes about downloading, converting, and working with YouTube media."

    def items(self):
        return Post.published.all()[:10]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.body

    def item_link(self, item):
        return item.get_absolute_url()

    def item_pubdate(self, item):
        return item.publish
