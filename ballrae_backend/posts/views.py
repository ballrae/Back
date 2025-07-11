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

        data = request.data.copy()
        data['post_title'] = title  # 필터링 없이 원본 저장
        data['post_content'] = content

        serializer = PostCreateSerializer(data=data)
        if serializer.is_valid():
            post = serializer.save(user=request.user)

            # ✅ Celery 백그라운드 작업으로 필터링 요청 보내기
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

class PostDetailView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    def get(self, request, team_id, post_id):
        try:
            post = Post.objects.get(id=post_id, team__id=team_id)
            
        except Post.DoesNotExist:
            return Response(
                {'status': 'error', 'message': '해당 게시글을 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PostDetailSerializer(post , context={'request' : request})

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