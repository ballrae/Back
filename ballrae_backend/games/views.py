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
    async def get(self, request, game_id, inning):
        date = game_id[:8]
        date_obj = datetime.strptime(date, '%Y%m%d').date()

        today = datetime.today().date()
        if date_obj == today: 
            # kafka 실행
            try:
                # Kafka에서 데이터 가져오기
                async def fetch_relay_data():
                    consumer = KafkaConsumer(
                        '2025', 
                        bootstrap_servers='kafka:9092',
                        auto_offset_reset='earliest',
                        enable_auto_commit=True,
                        group_id='new-group',
                        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                        key_deserializer=lambda k: k.decode('utf-8') if k else None
                    )

                    # Kafka에서 데이터를 비동기적으로 가져오는 방법
                    for message in consumer:
                        print(message)
                        if message.value.get('game_id') == game_id:
                            # 해당 이닝 데이터를 반환
                            top = message.value[f'{inning}회초']
                            bot = message.value[f'{inning}회말']

                            return top, bot  # Kafka에서 가져온 데이터
                        else: 
                            return None  # 데이터를 찾지 못했을 경우
                    return None
                
                # 실제 데이터를 가져오는 비동기 작업
                top, bot = await fetch_relay_data()

                if top:
                    top = kafka_to_front(top)
                    bot = kafka_to_front(bot)
                    return Response({
                        'status': 'OK',
                        'message': 'success',
                        'inning': inning,
                        'data': (top, bot)
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({
                        'status': 'error',
                        'message': '데이터를 찾을 수 없습니다.'
                    }, status=status.HTTP_404_NOT_FOUND) 
            
            except Exception as e:
                # Kafka에서 데이터 오류 처리
                return Response({
                    'status': 'error',
                    'message': f'Kafka 오류: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        elif date_obj < today:
            # db에서 호출
            try:
                game = Game.objects.get(id=game_id)
            except Game.DoesNotExist:
                return Response({
                    'status': 'OK',
                    'message': '경기가 없는 날입니다.'
                }, status=status.HTTP_200_OK)

            serializer = GameSerializer(game)
            return Response({
                'status': 'OK',
                'message': '게임 상세 조회 성공',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        
        else:
            # 아직 안한 경기
            return

    
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