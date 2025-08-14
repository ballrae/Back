from django.urls import path
from .views import PitchersView, BattersView, PlayerIdView, PlayerMainPageView, RealTimePlayersView
from ballrae_backend.games.views import PlayerView

urlpatterns = [
    path('pitcher/<int:id>/', PitchersView.as_view(), name='pitcher-view'),
    path('batter/<int:id>/', BattersView.as_view(), name='batter-view'),
    path('', PlayerView.as_view(), name='player-view'),
    path('player/id/', PlayerIdView.as_view(), name='player-id-view'),
    path('main/', PlayerMainPageView.as_view(), name='player-mainpage-view'),
    path('realtime/', RealTimePlayersView.as_view(), name='player-realtime-view'),
]