# posts/serializers.py

from rest_framework import serializers
from .models import Post

class PostSerializer(serializers.ModelSerializer):
    postId = serializers.IntegerField(source='id')
    title = serializers.CharField(source='post_title')
    createdAt = serializers.DateTimeField(source='post_created_at')  # ✅ 수정됨
    isPinned = serializers.BooleanField(source='is_pinned')

    class Meta:
        model = Post
        fields = ['postId', 'title', 'createdAt', 'isPinned']

class PostCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ['team', 'post_title', 'post_content', 'is_pinned']