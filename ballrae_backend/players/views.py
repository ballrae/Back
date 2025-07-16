# players/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime

# Create your views here.
class PlayersView(APIView):
    def get(self, request, player_id):
        return Response({
            'status': 'OK',
            'message': '선수 조회 성공',
            'data': "선수"
        }, status=status.HTTP_200_OK)
