from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Team
from .serializers import TeamSerializer

class TeamListView(APIView):
    def get(self, request):
        # ✅ 팀 이름 기준으로 정렬
        teams = Team.objects.all().order_by('team_name')
        serializer = TeamSerializer(teams, many=True)
        return Response({
            "status": "OK",
            "message": "구단 목록을 불러왔습니다.",
            "responseDto": serializer.data
        }, status=status.HTTP_200_OK)