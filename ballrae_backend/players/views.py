# players/views.py
from ballrae_backend.games.models import Player
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime
from .serializers import PitcherSerializer, BatterSerializer
from .models import Batter, Pitcher

class PitchersView(APIView):
    def get(self, request, name):
        try:
            player = Player.objects.filter(player_name=name).first()
            pitcher = Pitcher.objects.get(player=player)
            serializer = PitcherSerializer(pitcher)
            return Response({
                'status': 'OK',
                'message': '투수 기록 조회 성공',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'OK',
                'message': '투수 기록 조회 성공',
                'data': "존재하지 않는 투수입니다.",
                'error code': str(e)
            }, status=status.HTTP_200_OK)
        
class BattersView(APIView):
    def get(self, request, name):
        try:
            player = Player.objects.filter(player_name=name).first()
            batter = Batter.objects.get(player=player)
            serializer = BatterSerializer(batter)
            return Response({
                'status': 'OK',
                'message': '타자 기록 조회 성공',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'OK',
                'message': '타자 기록 조회 성공',
                'data': "존재하지 않는 타자입니다.",
                'error code': str(e)
            }, status=status.HTTP_200_OK)