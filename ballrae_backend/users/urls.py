from django.urls import path
from .views import KakaoLogin

urlpatterns = [
   path('kakao/', KakaoLogin.as_view(), name='kakao_login'),
]