# posts/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Post
from .serializers import PostSerializer, PostCreateSerializer
from rest_framework.permissions import IsAuthenticated

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