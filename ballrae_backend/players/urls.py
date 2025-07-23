from django.urls import path
from .views import PitchersView, BattersView

urlpatterns = [
    path('pitcher/<int:id>/', PitchersView.as_view(), name='player-view'), # 중계 내용
    path('batter/<int:id>/', BattersView.as_view(), name='player-view'), # 중계 내용
]