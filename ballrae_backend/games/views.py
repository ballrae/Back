# games/views.py
from adrf.views import APIView
# from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Game
from .serializers import GameSerializer
from datetime import datetime
from kafka import KafkaConsumer
import asyncio
from .serializers import InningSerializer
import json

def get_play(at_bats):
    result = []
    for a in at_bats:
        r = {}
        r['batter'] = a['actual_batter']
        r['strike_zone'] = a['strike_zone']
        r['at_bat'] = a['pitch_sequence']
        r['result'] = a['result']
        result.append(r)

    return result

def kafka_to_front(data):
    result = {}
    result['inning'] = data['inning']
    result['half'] = data['half']
    result['play_by_play'] = get_play(data['at_bats'])
    return result

# Game 목록 조회
class GameListView(APIView):
    def get(self, request, date):
        date_obj = datetime.strptime(date, '%Y%m%d').date()
        try:
            games = Game.objects.filter(date__date=date_obj)
            serializer = GameSerializer(games, many=True)
            return Response({
                'status': 'OK',
                'message': '게임 목록 조회 성공',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except:
            return Response({
                'status': 'OK',
                'message': '게임 목록 조회 성공',
                'data': "경기가 없는 날입니다."
            }, status=status.HTTP_200_OK)

# Game 상세 조회
class GameRelayView(APIView):
    def get(self, request, game_id, inning):
        date = game_id[:8]
        date_obj = datetime.strptime(date, '%Y%m%d').date()
        today = datetime.today().date()

        try:
            game = Game.objects.prefetch_related(
                'innings__atbats__pitches'
            ).get(id=game_id)
        except Game.DoesNotExist:
            return Response({'message': '경기 정보 없음'}, status=status.HTTP_404_NOT_FOUND)

        # 해당 이닝만 필터링
        inning_obj = game.innings.filter(inning_number=inning).first()
        if not inning_obj:
            return Response({'message': f'{inning}회 이닝 정보가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        # 이닝 하나만 serialize
        from .serializers import InningSerializer  # 필요 시 import
        inning_serializer = InningSerializer(inning_obj)

        if date_obj == today:
            return Response({
                'status': 'OK_REALTIME',
                'message': f'{inning}회 이닝 정보 (실시간)',
                'data': inning_serializer.data
            }, status=status.HTTP_200_OK)
        elif date_obj < today:
            return Response({
                'status': 'OK_ARCHIVED',
                'message': f'{inning}회 이닝 정보 (과거 경기)',
                'data': inning_serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({'message': '예정된 경기입니다.'}, status=status.HTTP_200_OK)
    
# Game 선수 조회
class GamePlayerView(APIView):
    def get(self, request, game_id):
        try:
            game = Game.objects.get(id=game_id)
        except Game.DoesNotExist:
            return Response({
                'status': 'error',
                'message': '선수를 찾을 수 없습니다.'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = GameSerializer(game)
        return Response({
            'status': 'OK',
            'message': '선수 상세 조회 성공',
            'data': serializer.data
        }, status=status.HTTP_200_OK)