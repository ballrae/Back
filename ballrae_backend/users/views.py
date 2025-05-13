from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import requests

# 간단한 test 코드
# 변경할거임

class KakaoLogin(APIView):
    def post(self, request, *args, **kwargs):
        access_token = request.data.get('access_token')

        if not access_token:
            return Response({
                "status": "error",
                "message": "No access token provided."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 카카오 사용자 정보 요청
        url = "https://kapi.kakao.com/v2/user/me"
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            return Response({
                "status": "error",
                "message": f"Kakao API 호출 실패 (status {response.status_code})"
            }, status=status.HTTP_400_BAD_REQUEST)

        # 응답 성공하면 그냥 연결됐다고 응답
        return Response({
            "status": "success",
            "message": "카카오 access token 연동 성공!",
            "kakao_raw": response.json()  # 원하면 이걸 빼도 돼
        }, status=status.HTTP_200_OK)