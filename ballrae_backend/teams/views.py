from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Team
from .serializers import TeamSerializer

class TeamListView(APIView):
    def get(self, request):
        teams = Team.objects.all()
        serializer = TeamSerializer(teams, many=True)
        return Response({
            "status": "OK",
            "message": "구단 목록을 불러왔습니다.",
            "responseDto": sorted(
                serializer.data,
                key=lambda x: x.get("win_percentage", 0),
                reverse=True
            )
        }, status=status.HTTP_200_OK)