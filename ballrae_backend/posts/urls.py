from django.urls import path
from .views import TeamPostListView, PostCreateView

urlpatterns = [
    path('create/', PostCreateView.as_view(), name='create-post'), # 게시글 작성 / 이러한 동적 경로 먼저 둬야함!!!
    path('<str:team_id>/', TeamPostListView.as_view(), name='team-posts'), #구단별 게시글 목ㅎ록
]