# posts/serializers.py
from rest_framework import serializers
from .models import Post
from .models import Comment

class PostSerializer(serializers.ModelSerializer):
    postId = serializers.IntegerField(source='id')
    title = serializers.CharField(source='post_title')
    createdAt = serializers.DateTimeField(source='post_created_at')  #  수정됨
    isPinned = serializers.BooleanField(source='is_pinned')

    class Meta:
        model = Post
        fields = ['postId', 'title', 'createdAt', 'isPinned'] # 프론트로 get으로보내니까 단순화 


class PostCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ['team', 'post_title', 'post_content', 'is_pinned'] # 프론트에서 post로 받아오니까 컬럼명이랑 동일하게
    
from rest_framework import serializers
from .models import Post

class PostDetailSerializer(serializers.ModelSerializer):
    postId = serializers.IntegerField(source='id')
    title = serializers.CharField(source='post_title')
    content = serializers.CharField(source='post_content')
    createdAt = serializers.DateTimeField(source='post_created_at')
    isPinned = serializers.BooleanField(source='is_pinned')
    authorId = serializers.IntegerField(source='user.id')
    authorNickname = serializers.CharField(source='user.user_nickname')
    authorTeamId = serializers.CharField(source='user.team_id')
    authorTeamName = serializers.CharField(source='user.team.team_name') 

    # 좋아요
    likesCount = serializers.SerializerMethodField()
    isLiked = serializers.SerializerMethodField()
    
    class Meta:
        model = Post
        fields = [
            'postId',
            'title',
            'content',
            'createdAt',
            'isPinned',
            'authorId',
            'authorNickname',
            'authorTeamId',
            'authorTeamName',  
            'likesCount',
            'isLiked',
        ]
    def get_isLiked(self, obj):
        request = self.context.get('request')
        print("user:", request.user)  # 여기 추가해봐!
        if request and request.user.is_authenticated:
            return obj.likes.filter(user_id=request.user.id).exists()
        return False

    def get_likesCount(self, obj):
        return obj.likes.count()


from rest_framework import serializers
from .models import Comment

class CommentSerializer(serializers.ModelSerializer):
    userNickname = serializers.CharField(source='user.user_nickname', read_only=True)
    userTeamId = serializers.CharField(source='user.team_id', read_only=True)
    comment_created_at = serializers.DateTimeField(read_only=True)
    comment_content = serializers.CharField(read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'userNickname', 'userTeamId', 'comment_content', 'comment_created_at']

class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ['comment_content']