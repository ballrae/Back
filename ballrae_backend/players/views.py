# players/views.py
from ballrae_backend.games.models import Player
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime
from .serializers import  BatterSimpleSerializer, PitcherSimpleSerializer, PitcherSerializer, BatterSerializer
from .models import Batter, Pitcher
from .services import get_realtime_batter, get_realtime_pitcher        
from django.db.models import F, FloatField, ExpressionWrapper, Case, When, Value

class PitchersView(APIView):
    def get(self, request, id=None):
        # 지원: path param id, query param id, query param pcode
        id_param = id if id is not None else request.query_params.get('id')
        pcode_param = request.query_params.get('pcode')

        player = None
        if id_param is not None:
            try:
                player_id = int(id_param)
            except (TypeError, ValueError):
                return Response({
                    'status': 'Bad Request',
                    'message': '유효한 id를 입력해주세요.',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)
            player = Player.objects.filter(id=player_id).first()
        elif pcode_param:
            player = Player.objects.filter(pcode=pcode_param).first()
        else:
            return Response({
                'status': 'Bad Request',
                'message': 'id 또는 pcode를 쿼리 파라미터로 입력해주세요.',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        if not player:
            return Response({
                'status': 'Not Found',
                'message': '해당 선수 정보를 찾을 수 없습니다.',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            pitcher = Pitcher.objects.get(player=player, season=2025)
        except Pitcher.DoesNotExist:
            return Response({
                'status': 'Not Found',
                'message': '해당 선수는 투수 기록이 없습니다.',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            # annotate 지표 계산
            pitchers = Pitcher.objects.annotate(
                avg=ExpressionWrapper(
                    Case(
                        When(ab=0, then=Value(0)),
                        default=(F('singles') + F('doubles') + F('triples') + F('homeruns')) * 1.0 / F('ab'),
                        output_field=FloatField()
                    ),
                    output_field=FloatField()
                ),
                k9=ExpressionWrapper(
                    Case(
                        When(innings=0, then=Value(0)),
                        default=F('strikeouts') * 9.0 / F('innings'),
                        output_field=FloatField()
                    ),
                    output_field=FloatField()
                ),
                bb9=ExpressionWrapper(
                    Case(
                        When(innings=0, then=Value(0)),
                        default=F('walks') * 9.0 / F('innings'),
                        output_field=FloatField()
                    ),
                    output_field=FloatField()
                ),
                whip=ExpressionWrapper(
                    Case(
                        When(innings=0, then=Value(0)),
                        default=(F('walks') + F('singles') + F('doubles') + F('triples') + F('homeruns')) * 1.0 / F('innings'),
                        output_field=FloatField()
                    ),
                    output_field=FloatField()
                )
            )

            annotated_target = pitchers.get(player__id=player.id, season=2025)

            def get_percentile(values, target, reverse=False):
                try:
                    total = len(values)
                    if total == 0 or target is None:
                        return 0

                    values.sort()

                    if reverse:
                        # 낮을수록 좋은 지표: ERA, BB9, AVG, L 등
                        greater_count = sum(1 for val in values if val > target)
                        equal_count = sum(1 for val in values if val == target)
                        adjusted_rank = greater_count + (equal_count / 2.0)
                    else:
                        # 높을수록 좋은 지표: WAR, K9, SO, W 등
                        less_count = sum(1 for val in values if val < target)
                        equal_count = sum(1 for val in values if val == target)
                        adjusted_rank = less_count + (equal_count / 2.0)

                    percentile = round((adjusted_rank / total) * 100, 1)
                    return percentile
                except:
                    return 0

            # percentile 계산할 필드들
            fields = [
                ('w', False),
                ('l', True),
                ('strikeouts', False),
                ('era', True),
                ('war', False),
                ('avg', True),
                ('k9', False),
                ('bb9', True),
                ('whip', True),
            ]
            percentile_result = {}

            for field, reverse in fields:
                values = list(
                    pitchers.exclude(**{f"{field}__isnull": True}).values_list(field, flat=True)
                )
                target_value = getattr(annotated_target, field)
                percentile_result[f"{field}_percentile"] = get_percentile(values, target_value, reverse=reverse)

            serializer = PitcherSerializer(annotated_target)

            return Response({
                'status': 'OK',
                'message': '투수 기록 조회 + percentile 계산 성공',
                'data': {
                    **serializer.data,
                    'metrics': percentile_result
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'Error',
                'message': '투수 기록 조회 중 오류 발생',
                'data': None,
                'error code': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BattersView(APIView):
    def get(self, request, id=None):
        # 지원: path param id, query param id, query param pcode
        id_param = id if id is not None else request.query_params.get('id')
        pcode_param = request.query_params.get('pcode')

        player = None
        if id_param is not None:
            try:
                player_id = int(id_param)
            except (TypeError, ValueError):
                return Response({
                    'status': 'Bad Request',
                    'message': '유효한 id를 입력해주세요.',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)
            player = Player.objects.filter(id=player_id).first()
        elif pcode_param:
            player = Player.objects.filter(pcode=pcode_param).first()
        else:
            return Response({
                'status': 'Bad Request',
                'message': 'id 또는 pcode를 쿼리 파라미터로 입력해주세요.',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        if not player:
            return Response({
                'status': 'Not Found',
                'message': '해당 선수 정보를 찾을 수 없습니다.',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            batter = Batter.objects.get(player=player, season=2025)
        except Batter.DoesNotExist:
            return Response({
                'status': 'Not Found',
                'message': '해당 선수는 타자 기록이 없습니다.',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            # annotate에 0 나누기 방지 처리
            batters = Batter.objects.annotate(
                obp=ExpressionWrapper(
                    Case(
                        When(pa=0, then=Value(0)),
                        default=(F('singles') + F('doubles') + F('triples') + F('homeruns') + F('walks')) * 1.0 / F('pa'),
                        output_field=FloatField()
                    ),
                    output_field=FloatField()
                ),
                slg=ExpressionWrapper(
                    Case(
                        When(ab=0, then=Value(0)),
                        default=(F('singles') + 2 * F('doubles') + 3 * F('triples') + 4 * F('homeruns')) * 1.0 / F('ab'),
                        output_field=FloatField()
                    ),
                    output_field=FloatField()
                ),
                ops=ExpressionWrapper(
                    Case(
                        When(ab=0, then=Value(0)),
                        When(pa=0, then=Value(0)),
                        default=(
                            ((F('singles') + F('doubles') + F('triples') + F('homeruns') + F('walks')) * 1.0 / F('pa')) +
                            ((F('singles') + 2 * F('doubles') + 3 * F('triples') + 4 * F('homeruns')) * 1.0 / F('ab'))
                        ),
                        output_field=FloatField()
                    ),
                    output_field=FloatField()
                ),
                iso=ExpressionWrapper(
                    Case(
                        When(ab=0, then=Value(0)),
                        default=(
                            ((F('singles') + 2 * F('doubles') + 3 * F('triples') + 4 * F('homeruns')) * 1.0 / F('ab')) -
                            ((F('singles') + F('doubles') + F('triples') + F('homeruns')) * 1.0 / F('ab'))
                        ),
                        output_field=FloatField()
                    ),
                    output_field=FloatField()
                ),
                bb_k=ExpressionWrapper(
                    Case(
                        When(strikeouts=0, then=Value(0)),
                        default=F('walks') * 1.0 / F('strikeouts'),
                        output_field=FloatField()
                    ),
                    output_field=FloatField()
                )
            )

            annotated_target = batters.get(player__id=player.id, season=2025)

            def get_percentile(values, target):
                """
                values: 정렬된 리스트 (오름차순)
                target: 해당 타자의 값
                """
                try:
                    total = len(values)
                    if total == 0 or target is None:
                        return 0

                    # 동점자 처리: 전체 중 target보다 작은 개수 + target과 같은 값의 절반
                    less_count = sum(1 for val in values if val < target)
                    equal_count = sum(1 for val in values if val == target)
                    adjusted_rank = less_count + (equal_count / 2.0)

                    percentile = round((adjusted_rank / total) * 100, 1)
                    return percentile
                except Exception:
                    return 0

            fields = ['war', 'wrc', 'babip', 'obp', 'slg', 'ops', 'iso', 'bb_k', 'homeruns']
            percentile_result = {}

            for field in fields:
                values = list(
                    batters.exclude(**{f"{field}__isnull": True}).values_list(field, flat=True)
                )
                values.sort()
                target_value = getattr(annotated_target, field)
                percentile_result[f"{field}_percentile"] = get_percentile(values, target_value)

            serializer = BatterSerializer(annotated_target)

            return Response({
                'status': 'OK',
                'message': '타자 기록 조회 + percentile 계산 성공',
                'data': {
                    **serializer.data,
                    'metrics': percentile_result
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'Error',
                'message': '타자 기록 조회 중 오류 발생',
                'data': None,
                'error code': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
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
    def get(self, request):
        players = Player.objects.all().order_by("player_name")

        data = []

        for player in players:
            if player.position == "B":
                try:
                    batter = Batter.objects.get(player=player, season=2025)
                    serializer = BatterSimpleSerializer(batter)
                    data.append(serializer.data)
                except Batter.DoesNotExist:
                    continue  # 기록 없으면 스킵

            elif player.position == "P":
                try:
                    pitcher = Pitcher.objects.get(player=player, season=2025)
                    serializer = PitcherSimpleSerializer(pitcher)
                    data.append(serializer.data)
                except Pitcher.DoesNotExist:
                    continue

        return Response({
            "status": "OK",
            "message": f"전체 선수({len(data)}명) 정보 조회 성공",
            "data": data
        }, status=status.HTTP_200_OK)

class RealTimePlayersView(APIView):
    def get(self, request):
        pitcher = request.query_params.get("pitcher")
        batter = request.query_params.get("batter")
        
        p = Player.objects.filter(pcode=pitcher).first()
        b = Player.objects.filter(pcode=batter).first()

        bat = get_realtime_batter(b.pcode)
        pit = get_realtime_pitcher(p.pcode)

        return Response({
            "status": "OK",
            "message": "실시간 투타 정보",
            "data": {
                "batter": bat,
                "pitcher": pit
            }
        })