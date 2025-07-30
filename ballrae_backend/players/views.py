# players/views.py
from ballrae_backend.games.models import Player
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime
from .serializers import  BatterSimpleSerializer, PitcherSimpleSerializer, PitcherSerializer, BatterSerializer
from .models import Batter, Pitcher

def get_serializer_for_player(player_obj):
    if player_obj.position == "B":
        return BatterSimpleSerializer(Batter.objects.get(player=player_obj))
    elif player_obj.position == "P":
        return PitcherSimpleSerializer(Pitcher.objects.get(player=player_obj))
    
class PitchersView(APIView):
    def get(self, request, id):
        try:
            player = Player.objects.filter(id=id).first()
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
    def get(self, request, id):
        try:
            player = Player.objects.filter(id=id).first()
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
        
class PlayerIdView(APIView):
    def get(self, request):
        name = request.query_params.get("name")

        if not name:
            return Response({
                'status': 'Bad Request',
                'message': '선수 이름(name)을 쿼리 파라미터로 입력해주세요.',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        players = Player.objects.filter(player_name=name)
        if players.exists():
            return Response({
                'status': 'OK',
                'message': f'{name} 선수 ID 반환 성공',
                'data': [
                    {"id": player.id, "player_name": player.player_name}
                    for player in players
                ]
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': 'Not Found',
                'message': f'{name} 이름의 선수를 찾을 수 없습니다.',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)


class PlayerMainPageView(APIView):
    def get(self, request, id):
        try:
            player = Player.objects.get(id=id)
            serializer = get_serializer_for_player(player)

        except Player.DoesNotExist:
            return Response({
                "status": "Not Found",
                "message": "해당하는 선수를 찾을 수 없습니다.",
                "data": None
            }, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "status": "OK",
            "message": f"{player.player_name} 선수 정보 조회 성공",
            "data": serializer.data
        }, status=status.HTTP_200_OK)