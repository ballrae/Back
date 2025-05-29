# posts/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Post,  PostLike, Comment
from .serializers import CommentSerializer, CommentCreateSerializer  # 필요 시 CreateSerializer도 분리
from .serializers import PostSerializer, PostCreateSerializer, PostDetailSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import get_object_or_404

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
        serializer = PostCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)  # 현재 로그인한 유저 할당
            return Response({'status': 'OK', 'message': '작성 완료'}, status=status.HTTP_201_CREATED)
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
        serializer = CommentCreateSerializer(data=request.data)  # ✅ Create 전용 serializer 사용
        if serializer.is_valid():
            serializer.save(user=request.user, post=post)
            read_serializer = CommentSerializer(serializer.instance)  # ✅ 저장된 결과로 다시 serialize
            return Response({
                'status': 'OK',
                'message': '댓글 등록 완료',
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