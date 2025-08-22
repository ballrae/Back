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

def get_player_map(pcode):
    player = Player.objects.filter(pcode=pcode).first()
    result = {
                "id": player.id,
                "pcode": player.pcode,
                "player_name": player.player_name
            }
    return result

def enrich_atbats_with_players(inning_data: dict) -> dict:
    """Redis에서 불러온 at_bats에 player 이름/ID 붙이기."""
    at_bats = inning_data.get("atbats", [])
    player_map = {}

    for ab in at_bats:
        actual_batter = ab.get("actual_batter")
        original_batter = ab.get("original_batter")
        pitcher = ab.get("pitcher")

        if actual_batter:
            player_map['actual_batter'] = get_player_map(actual_batter)
            ab["actual_batter"] = player_map['actual_batter']

        if original_batter:
            player_map['original_batter'] = get_player_map(original_batter)
            ab["original_batter"] = player_map['original_batter']

        if pitcher:
            player_map['pitcher'] = get_player_map(pitcher)    
            ab["pitcher"] = player_map['pitcher']

    return inning_data

def update_game_statuses():
    # scheduled인데 시작 시간이 지난 경기 → ing
    kst = timezone.now().astimezone(pytz.timezone('Asia/Seoul'))
    print(kst)

    Game.objects.filter(status='scheduled', date__lte=kst).update(status='ing')

# Game 목록 조회
class GameListView(APIView):
    def get(self, request, date):
        update_game_statuses()

        try:
            games = Game.objects.filter(id__startswith=date)
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
                data['top'] = enrich_atbats_with_players(data['top'])

            if bot_raw:
                data['bot'] = json.loads(bot_raw.decode() if isinstance(bot_raw, bytes) else bot_raw)
                data['bot'] = enrich_atbats_with_players(data['bot'])

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

# 문자 중계 기반 오늘 성적
class PlayerTodayStatsView(APIView):
    def get(self, request):
        """
        쿼리 파라미터:
        - pcode: 선수 pcode (필수)
        - date: 조회 날짜(YYYYMMDD, 기본값: 오늘)
        """
        pcode = request.query_params.get("pcode")
        date_str = request.query_params.get("date")
        if not pcode:
            return Response({"status": "FAIL", "message": "pcode(선수 코드)가 필요합니다."}, status=400)

        if date_str:
            try:
                date = datetime.strptime(date_str, "%Y%m%d").date()
                date_prefix = date_str

                # 선수의 소속팀에 해당하는 경기만 조회하도록 team_id 사용
                team_id = None
                try:
                    player_obj = Player.objects.get(pcode=pcode)
                    team_id = player_obj.team_id
                except Player.DoesNotExist:
                    team_id = None
            except Exception:
                return Response({"status": "FAIL", "message": "날짜 형식이 올바르지 않습니다. (YYYYMMDD)"}, status=400)
        else:
            date = datetime.now().date()
            date_prefix = date.strftime("%Y%m%d")

        try:
            player = Player.objects.get(pcode=pcode)
        except Player.DoesNotExist:
            return Response({"status": "FAIL", "message": "해당 선수를 찾을 수 없습니다."}, status=404)

        # id가 date_prefix로 시작하는 경기 찾기
        games = Game.objects.filter(id__startswith=date_prefix)
        if not games.exists():
            return Response({"status": "FAIL", "message": f"{date_prefix}에 열린 경기가 없습니다."}, status=404)

        # 오늘 경기에서 해당 선수의 atbat 기록 찾기 (player__pcode로 비교)
        atbats = AtBat.objects.filter(game__in=games, player__pcode=pcode)
        if not atbats.exists():
            return Response({
                "status": "OK",
                "message": f"{player.player_name} 선수의 {date_prefix} 경기 기록이 없습니다.",
                "data": {}
            }, status=200)

        # 타자/투수 구분
        if player.position == "B":
            ab = atbats.count()
            hits = atbats.filter(result__in=["안타", "2루타", "3루타", "홈런"]).count()
            homeruns = atbats.filter(result="홈런").count()
            walks = atbats.filter(result__in=["볼넷", "사구", "고의4구"]).count()
            strikeouts = atbats.filter(result="삼진").count()
            rbi = atbats.aggregate(rbi_sum=models.Sum("rbi"))["rbi_sum"] or 0

            avg = round(hits / ab, 3) if ab else 0.0
            pa = ab + walks
            obp = round((hits + walks) / pa, 3) if pa else 0.0

            data = {
                "ab": ab,
                "hits": hits,
                "homeruns": homeruns,
                "walks": walks,
                "strikeouts": strikeouts,
                "rbi": rbi,
                "avg": avg,
                "obp": obp,
                "detail": [
                    {
                        "inning": atbat.inning,
                        "result": atbat.result,
                        "rbi": atbat.rbi,
                        "description": atbat.description
                    }
                    for atbat in atbats.order_by("inning")
                ]
            }
        elif player.position == "P":
            outs = atbats.filter(result__in=["땅볼아웃", "뜬공아웃", "삼진", "병살", "희생플라이"]).count()
            innings = round(outs / 3, 1) if outs else 0.0
            strikeouts = atbats.filter(result="삼진").count()
            walks = atbats.filter(result__in=["볼넷", "사구", "고의4구"]).count()
            hits = atbats.filter(result__in=["안타", "2루타", "3루타", "홈런"]).count()
            homeruns = atbats.filter(result="홈런").count()

            data = {
                "innings": innings,
                "strikeouts": strikeouts,
                "walks": walks,
                "hits": hits,
                "homeruns": homeruns,
                "detail": [
                    {
                        "inning": atbat.inning,
                        "result": atbat.result,
                        "description": atbat.description
                    }
                    for atbat in atbats.order_by("inning")
                ]
            }
        else:
            return Response({"status": "FAIL", "message": "선수 포지션 정보가 없습니다."}, status=400)

        return Response({
            "status": "OK",
            "message": f"{player.player_name} 선수의 {date_prefix} 경기 성적",
            "data": data
        }, status=200)