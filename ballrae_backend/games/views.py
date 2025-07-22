# games/views.py
from adrf.views import APIView
# from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Game
from .serializers import GameSerializer, InningSerializer, GameDateSerializer
from datetime import datetime

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

        inning_data = {}
        # 해당 이닝만 필터링
        inning_objs = game.innings.filter(inning_number=inning)

        print(inning_objs)
        if not inning_objs:
            return Response({'message': f'{inning}회 이닝 정보가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        else:
            inning_data['top'] = InningSerializer(inning_objs[0]).data
            inning_data['bot'] = InningSerializer(inning_objs[1]).data

        if date_obj == today:
            return Response({
                'status': 'OK_REALTIME',
                'message': f'{inning}회 이닝 정보 (실시간)',
                'data': inning_data
            }, status=status.HTTP_200_OK)
        elif date_obj < today:
            return Response({
                'status': 'OK_ARCHIVED',
                'message': f'{inning}회 이닝 정보 (과거 경기)',
                'data': inning_data
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