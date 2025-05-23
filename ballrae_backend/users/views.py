from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
import requests
from .models import User
from .serializers import TeamUpdateSerializer

# JWT 토큰 발급
def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

# 카카오 로그인
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

        # DB 저장 or 조회 (kakao_id 기준)
        user, created = User.objects.get_or_create(
            kakao_id=kakao_id,
            defaults={
                'user_nickname': nickname
            }
        )

        # 닉네임 갱신 로직 추가 ✅
        if not created and user.user_nickname.startswith('user_'):
            user.user_nickname = nickname
            user.save()

        tokens = get_tokens_for_user(user)

        return Response({
            "status": "success",
            "message": "로그인 및 JWT 발급 성공",
            "data": {
                "user_id": user.id,  #  기본키 필드는 이제 user.id 로 사용
                "kakao_id": user.kakao_id,
                "user_nickname": user.user_nickname,
                "created_at": user.created_at,
                "team_name": user.team.team_name if user.team else None,   # ✅ 추가
                "team_id": user.team.id if user.team else None,   # ✅ 추가
                "tokens": tokens
            }
        }, status=200)

# 마이팀 설정
class SetMyTeamView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        user = request.user  # JWT로 인증된 현재 유저
        serializer = TeamUpdateSerializer(user, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({
                "status": "success",
                "message": "마이팀이 설정되었습니다.",
                "team_id": serializer.data['team_id']
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

# 유저 정보 조회
class MyInfoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "user_nickname": user.user_nickname,
            "team_id": user.team.id if user.team else None,
            "team_name": user.team.team_name if user.team else None,
        }, status=200)