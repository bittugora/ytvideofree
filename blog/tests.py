from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from blog.models import Tag, Post

class TagModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Tag.objects.create(name='testtag')

    def test_name_label(self):
        tag = Tag.objects.get(id=1)
        field_label = tag._meta.get_field('name').verbose_name
        self.assertEqual(field_label, 'name')

    def test_name_max_length(self):
        tag = Tag.objects.get(id=1)
        max_length = tag._meta.get_field('name').max_length
        self.assertEqual(max_length, 40)

    def test_object_name_is_name(self):
        tag = Tag.objects.get(id=1)
        expected_object_name = f'{tag.name}'
        self.assertEqual(expected_object_name, str(tag))

class PostModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_user = get_user_model().objects.create_user(username='testuser', password='testpass')
        Post.objects.create(
            title='test post',
            slug='test-post',
            author=test_user,
            body='This is a test post.',
            publish=timezone.now(),
            status='PB'
        )

    def test_title_label(self):
        post = Post.objects.get(id=1)
        field_label = post._meta.get_field('title').verbose_name
        self.assertEqual(field_label, 'title')

    def test_title_max_length(self):
        post = Post.objects.get(id=1)
        max_length = post._meta.get_field('title').max_length
        self.assertEqual(max_length, 100)

    def test_object_name_is_title(self):
        post = Post.objects.get(id=1)
        expected_object_name = f'{post.title}'
        self.assertEqual(expected_object_name, str(post))

    def test_get_absolute_url(self):
        post = Post.objects.get(id=1)
        expected_url = reverse('post_detail', kwargs={'slug': post.slug})
        self.assertEqual(expected_url, post.get_absolute_url())
