from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
import requests
from .models import User  # ← 이거 잊지 마!

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

class KakaoLogin(APIView):
    def post(self, request, *args, **kwargs):
        access_token = request.data.get('access_token')
        if not access_token:
            return Response({"status": "error", "message": "No access token provided."}, status=400)

        # 카카오 사용자 정보 요청
        url = "https://kapi.kakao.com/v2/user/me"
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            return Response({"status": "error", "message": "Kakao API 호출 실패"}, status=400)

        user_info = response.json()
        kakao_id = str(user_info.get('id'))
        nickname = user_info.get('properties', {}).get('nickname') or f"user_{kakao_id}"

        # DB 저장 or 조회
        user, created = User.objects.get_or_create(
            user_id=kakao_id,
            defaults={'username': nickname}
        )

        #  JWT 발급
        tokens = get_tokens_for_user(user)

        return Response({
            "status": "success",
            "message": "로그인 및 JWT 발급 성공",
            "data": {
                "user_id": user.user_id,
                "username": user.username,
                "tokens": tokens
            }
        }, status=200)