from django.urls import path
from .views import GameListView, GameRelayView, GamePlayerView

urlpatterns = [
    path('gamelist/<str:date>', GameListView.as_view(), name='game-list'), # 경기 목록
    path('<str:game_id>/relay/<int:inning>/', GameRelayView.as_view(), name='game-relay'), # 중계 내용
    path('<str:team_id>/relay/<int:post_id>/', GamePlayerView.as_view(), name='game-player'), # 선수 정보
]