from django.urls import path
from .views import PitchersView, BattersView

urlpatterns = [
    path('pitcher/<str:name>/', PitchersView.as_view(), name='player-view'), # 중계 내용
    path('batter/<str:name>/', BattersView.as_view(), name='player-view'), # 중계 내용
]