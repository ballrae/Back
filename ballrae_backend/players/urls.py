from django.urls import path
from .views import PlayersView

urlpatterns = [
    path('<str:player_id>/', PlayersView.as_view(), name='player-view'), # 중계 내용
]