# posts/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Post,  PostLike, Comment
from .serializers import CommentSerializer, CommentCreateSerializer  # 필요 시 CreateSerializer도 분리
from .serializers import PostSerializer, PostCreateSerializer, PostDetailSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import get_object_or_404

from .tasks import filter_post_text_task
from .tasks import filter_comment_text_task

from django.utils import timezone
from datetime import timedelta

class TeamPostListView(APIView):
    def get(self, request, team_id):
        posts = Post.objects.filter(team__id=team_id).order_by('-is_pinned', '-post_created_at')
        serializer = PostSerializer(posts, many=True)

        return Response({
            'status': 'OK',
            'message': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    

class PostCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        title = request.data.get('post_title', '')
        content = request.data.get('post_content', '')

        # 최근 30초 이내에 작성한 게시글이 있는지 확인
        now = timezone.now()
        time_threshold = now - timedelta(seconds=30)
        recent_post = Post.objects.filter(user=request.user, post_created_at__gte=time_threshold).exists()

        if recent_post:
            return Response({
                'status': 'error',
                'message': '30초 이내에 작성한 게시글이 있습니다. 잠시 후 다시 시도해주세요.'
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        data = request.data.copy()
        data['post_title'] = title
        data['post_content'] = content

        serializer = PostCreateSerializer(data=data)
        if serializer.is_valid():
            post = serializer.save(user=request.user)

            filter_post_text_task.delay(post.id, title, content)

            return Response({
                'status': 'OK',
                'message': '작성 완료 (필터링 중)',
                'data': {
                    'postId': post.id
                }
            }, status=status.HTTP_201_CREATED)

        return Response({'status': 'error', 'message': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
from rest_framework.permissions import IsAuthenticatedOrReadOnly

# views.py
import time

class PostDetailView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request, team_id, post_id):
        start_time = time.time()

        try:
            post = Post.objects.select_related('user__team', 'team') \
                               .prefetch_related('likes') \
                               .get(id=post_id, team__id=team_id)
        except Post.DoesNotExist:
            return Response({'status': 'error', 'message': '해당 게시글을 찾을 수 없습니다.'},
                            status=status.HTTP_404_NOT_FOUND)

        likes_qs = post.likes.all()
        likes_count = likes_qs.count()
        is_liked = request.user.is_authenticated and likes_qs.filter(user_id=request.user.id).exists()

        serializer = PostDetailSerializer(post, context={
            'request': request,
            'likes_count': likes_count,
            'is_liked': is_liked
        })

        print(f"[PostDetailView] 처리 시간: {time.time() - start_time:.3f}초")

        return Response({
            'status': 'OK',
            'message': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)

# 댓글 작성  + 리스트
class CommentListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, team_id, post_id):
        post = get_object_or_404(Post, id=post_id, team__id=team_id)
        comments = Comment.objects.filter(post=post).order_by('comment_created_at')
        serializer = CommentSerializer(comments, many=True)
        return Response({
            'status': 'OK',
            'message': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request, team_id, post_id):
        post = get_object_or_404(Post, id=post_id, team__id=team_id)

        original_text = request.data.get('comment_content', '')  # 원본만 저장
        data = request.data.copy()
        data['comment_content'] = original_text

        serializer = CommentCreateSerializer(data=data)
        if serializer.is_valid():
            comment = serializer.save(user=request.user, post=post)

            # ✅ 필터링을 Celery로 백그라운드 처리
            filter_comment_text_task.delay(comment.id, original_text)

            read_serializer = CommentSerializer(comment)
            return Response({
                'status': 'OK',
                'message': '댓글 등록 완료 (필터링 중)',
                'data': read_serializer.data
            }, status=status.HTTP_201_CREATED)

        return Response({
            'status': 'error',
            'message': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

# 좋아요 
class TogglePostLikeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, team_id, post_id):  # ✅ team_id도 받도록!
        post = get_object_or_404(Post, id=post_id, team__id=team_id)
        user = request.user

        like, created = PostLike.objects.get_or_create(post=post, user=user)

        if not created:
            like.delete()
            return Response({
                'status': 'OK',
                'message': '좋아요 취소됨',
                'data': {
                    'isLiked': False,
                    'likesCount': post.likes.count()
                }
            }, status=status.HTTP_200_OK)

        return Response({
            'status': 'OK',
            'message': '좋아요 등록됨',
            'data': {
                'isLiked': True,
                'likesCount': post.likes.count()
            }
        }, status=status.HTTP_201_CREATED)


