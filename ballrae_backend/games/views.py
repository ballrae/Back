# games/views.py
from adrf.views import APIView
# from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Game, Player
from .serializers import GameSerializer, InningSerializer, GameDateSerializer, PlayerSerializer
from datetime import datetime
from ballrae_backend.streaming.redis_client import redis_client
import json

TEAM_CODE = {
    "HH": "한화",
    "DS": "두산",
    "KT": "kt",
    "LG": "LG",
    "KA": "KIA",
    "LT": "롯데",
    "SS": "삼성",
    "HE": "키움",
    "NC": "NC",
    "SL": "SSG",
}

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
            serializer = GameDateSerializer(games, many=True)
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

class GameRelayView(APIView):
    def get(self, request, game_id, inning):
        date = game_id[:8]
        date_obj = datetime.strptime(date, '%Y%m%d').date()
        inning = int(inning)  # URL에서 넘어온건 문자열일 수 있음

        # Redis에서 실시간 여부 판단
        realtime_top_key = f"game:{game_id}:inning:{inning}:top"
        realtime_bot_key = f"game:{game_id}:inning:{inning}:bot"

        # Redis 캐시가 있으면 실시간 경기로 판단
        if redis_client.exists(realtime_top_key) and redis_client.exists(realtime_bot_key):
            top_data = json.loads(redis_client.get(realtime_top_key))
            bot_data = json.loads(redis_client.get(realtime_bot_key))
            return Response({
                'status': 'OK_REALTIME',
                'message': f'{inning}회 이닝 정보 (실시간)',
                'data': {
                    'top': top_data,
                    'bot': bot_data
                }
            }, status=status.HTTP_200_OK)

        # Redis에 없으면 → DB 조회 (과거 경기)
        try:
            game = Game.objects.prefetch_related(
                'innings__atbats__pitches'
            ).get(id=game_id)
        except Game.DoesNotExist:
            return Response({'message': '경기 정보 없음'}, status=status.HTTP_404_NOT_FOUND)

        inning_objs = game.innings.filter(inning_number=inning)

        if not inning_objs:
            return Response({'message': f'{inning}회 이닝 정보가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        inning_data = {
            'top': InningSerializer(inning_objs[0]).data,
            'bot': InningSerializer(inning_objs[1]).data
        }

        return Response({
            'status': 'OK_ARCHIVED',
            'message': f'{inning}회 이닝 정보 (과거 경기)',
            'data': inning_data
        }, status=status.HTTP_200_OK)
    
# 선수 조회
class PlayerView(APIView):
    def get(self, request):
        players = Player.objects.all().order_by('player_name')
        msg = "전체 선수"

        name = request.query_params.get("name")
        team = request.query_params.get("team")
        size = request.query_params.get("size")

        if name:
            players = players.filter(player_name=name)
            msg = f"{name} 선수"

        if team:
            players = players.filter(team_id=team)
            msg = f"{TEAM_CODE.get(team, team)} 소속 선수"

        if size:
            try:
                size = int(size)
                players = players.order_by("?")[:size]
                msg = f"{msg}, 무작위 {size}명"
            except ValueError:
                return Response({"status": "FAIL", "message": "유효하지 않은 size입니다."}, status=400)

        serializer = PlayerSerializer(players, many=True)
        return Response({
            'status': 'OK',
            'message': f"{msg} 조회 성공",
            'data': serializer.data
        }, status=status.HTTP_200_OK)
