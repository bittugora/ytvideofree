from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import Tag, Post

class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'status', 'created', 'updated')
    list_filter = ('status', 'created', 'updated')
    search_fields = ('title', 'body')
    prepopulated_fields = {'slug': ('title',)}
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser and not request.user.is_staff:
            form.base_fields['author'].disabled = True
        return form
    
    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and not request.user.is_staff:
            return
        super().save_model(request, obj, form, change)

admin.site.register(Tag)
admin.site.register(Post, PostAdmin)
