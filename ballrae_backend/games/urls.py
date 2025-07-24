from django.urls import path
from .views import GameListView, GameRelayView

urlpatterns = [
    path('gamelist/<str:date>', GameListView.as_view(), name='game-list'), # 경기 목록
    path('<str:game_id>/relay/<int:inning>/', GameRelayView.as_view(), name='game-relay'), # 중계 내용
]