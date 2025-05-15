from django.urls import path
from .views import KakaoLogin
from .views import SetMyTeamView

urlpatterns = [
   path('kakao/', KakaoLogin.as_view(), name='kakao_login'),
   path('myteam/', SetMyTeamView.as_view(), name='set-my-team'),
]