from django.urls import path
from .views import PitchersView, BattersView, PlayerIdView, PlayerMainPageView
from ballrae_backend.games.views import PlayerView

urlpatterns = [
    path('pitcher/<int:id>/', PitchersView.as_view(), name='pitcher-view'),
    path('batter/<int:id>/', BattersView.as_view(), name='batter-view'),
    path('', PlayerView.as_view(), name='player-view'),
    path('player/id/', PlayerIdView.as_view(), name='player-id-view'),
    path('main/<int:id>/', PlayerMainPageView.as_view(), name='player-mainpage-view'),
]