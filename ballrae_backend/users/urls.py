from django.urls import path
from .views import KakaoLogin, SetMyTeamView, MyInfoView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
   path('kakao/', KakaoLogin.as_view(), name='kakao_login'),
   path('myteam/', SetMyTeamView.as_view(), name='set-my-team'),
   path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'), 
   path('me/', MyInfoView.as_view(), name='my-info'), 
]
