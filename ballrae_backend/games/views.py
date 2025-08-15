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
from django.utils import timezone
from ballrae_backend.games.models import Game
import pytz

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

def update_game_statuses():
    # scheduled인데 시작 시간이 지난 경기 → ing
    kst = timezone.now().astimezone(pytz.timezone('Asia/Seoul'))
    print(kst)

    Game.objects.filter(status='scheduled', date__lte=kst).update(status='ing')

# Game 목록 조회
class GameListView(APIView):
    def get(self, request, date):
        update_game_statuses()

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

POSITION_MAP = {
    "1": "투수", "2": "포수", "3": "1루수", "4": "2루수", "5": "3루수",
    "6": "유격수", "7": "좌익수", "8": "중견수", "9": "우익수", "10": "지명타자",
}

def _hgetall_str(key: str) -> dict[str, str]:
    """Redis HGETALL 결과를 모두 str로 표준화 (bytes/str 혼용 안전)."""
    raw = redis_client.hgetall(key)
    if not raw:
        return {}
    out = {}
    for k, v in raw.items():
        if isinstance(k, bytes):
            k = k.decode()
        if isinstance(v, bytes):
            v = v.decode()
        out[str(k)] = str(v)
    return out

def _defense_positions_with_names(game_id: str, code) -> dict:
    """Redis 해시(수비 포지션) -> 이름/포지션명으로 변환해서 반환."""

    key = f"defense_position:{game_id}:{code}"

    def_map = _hgetall_str(key)  # {pcode: "포지션번호"}

    # print(home_map, away_map)

    pcodes = list(set(def_map.keys()))
    name_map = {
        str(p["pcode"]): p["player_name"]
        for p in Player.objects.filter(pcode__in=pcodes).values("pcode", "player_name")
    }

    def enrich(m: dict[str, str]) -> dict:
        result = {}
        for pcode in m.keys():
            result[POSITION_MAP.get(str(m.get(pcode, "")), str(m.get(pcode, "")))] = name_map.get(pcode, pcode)

        return result

    return enrich(def_map)
    

class GameRelayView(APIView):
    def get(self, request, game_id, inning):
        inning = int(inning)

        top_key = f"game:{game_id}:inning:{inning}:top"
        bot_key = f"game:{game_id}:inning:{inning}:bot"

        top_raw = redis_client.get(top_key)
        bot_raw = redis_client.get(bot_key)

        # Redis에 하나라도 있으면 실시간 응답
        if top_raw or bot_raw:
            data = {}
            if top_raw:
                data['top'] = json.loads(top_raw.decode() if isinstance(top_raw, bytes) else top_raw)
            if bot_raw:
                data['bot'] = json.loads(bot_raw.decode() if isinstance(bot_raw, bytes) else bot_raw)

            away_code = game_id[8:10]
            home_code = game_id[10:12]

            data['defense_positions'] = {
                'home_team': home_code,
                'away_team': away_code,
                'home': _defense_positions_with_names(game_id, home_code),
                'away': _defense_positions_with_names(game_id, away_code),
            }

            return Response({
                'status': 'OK_REALTIME',
                'message': f'{inning}회 이닝 정보 (실시간)',
                'data': data
            }, status=status.HTTP_200_OK)

        # 없으면 DB 조회
        try:
            game = Game.objects.prefetch_related('innings__atbats__pitches').get(id=game_id)
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
