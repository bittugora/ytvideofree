# blog/models.py
from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User

class Tag(models.Model):
    name = models.CharField(max_length=40)

    def __str__(self):
        return self.name
    
class PublishedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status=Post.Status.PUBLISHED)

class Post(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DF', 'Draft'
        PUBLISHED = 'PB', 'Published'

    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique_for_date='publish')
    author = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, null=True, blank=True)

    body = models.TextField()
    image = models.ImageField(upload_to='', blank=True, null=True)
    tags = models.ManyToManyField(Tag, blank=True)
    publish = models.DateTimeField(default=timezone.now)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now= True)
    status = models.CharField(max_length=2,choices=Status.choices,default=Status.DRAFT)
    
    objects = models.Manager() # The default manager.
    published = PublishedManager() # Our custom manager.

    class Meta:
        ordering = ['-publish']

    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse("post_detail", kwargs={"slug": self.slug})
