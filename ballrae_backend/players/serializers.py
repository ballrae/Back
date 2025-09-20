# players/serializers.py
from rest_framework import serializers
from .models import Batter, Pitcher
from ballrae_backend.games.serializers import PlayerSerializer
from ballrae_backend.games.models import Player

class PitcherSerializer(serializers.ModelSerializer):
    player = PlayerSerializer(read_only=True)
    stats = serializers.SerializerMethodField()

    def get_stats(self, obj):
        ab = obj.ab or 0
        pa = obj.pa or 0
        hits = (obj.singles or 0) + (obj.doubles or 0) + (obj.triples or 0) + (obj.homeruns or 0)

        if pa:
            walks = obj.walks
            inn = obj.innings
            avg = round(hits / ab, 3) if ab else 0.0
            slg = round(
                ((obj.singles or 0) +
                2 * (obj.doubles or 0) +
                3 * (obj.triples or 0) +
                4 * (obj.homeruns or 0)) / ab, 3
            ) if ab else 0.0

            obp = round((hits + (obj.walks or 0)) / pa, 3) if pa else 0.0

            ops = round(obp + slg, 3)

            k9 = round(obj.strikeouts * 9 / inn, 2)
            bb9 = round(obj.walks * 9 /inn, 2)

            whip = round((walks+hits)/inn, 2)

            return {
                "avg": avg,
                "slg": slg,
                "obp": obp,
                "ops": ops,
                "k/9": k9,
                "bb/9": bb9,
                "whip": whip,
            }
        else: return {}    

    class Meta:
        model = Pitcher
        fields = '__all__'

class BatterSerializer(serializers.ModelSerializer):
    player = PlayerSerializer(read_only=True)
    stats = serializers.SerializerMethodField()
    raa_data = serializers.SerializerMethodField()

    def get_stats(self, obj):
        ab = obj.ab or 0
        pa = obj.pa or 0
        hits = (obj.singles or 0) + (obj.doubles or 0) + (obj.triples or 0) + (obj.homeruns or 0)

        if pa:
            avg = round(hits / ab, 3) if ab else 0.0
            slg = round(
                ((obj.singles or 0) +
                2 * (obj.doubles or 0) +
                3 * (obj.triples or 0) +
                4 * (obj.homeruns or 0)) / ab, 3
            ) if ab else 0.0

            obp = round((hits + (obj.walks or 0)) / pa, 3) if pa else 0.0

            ops = round(obp + slg, 3)

            isop = round(slg - avg, 3)

            bbk = round(obj.walks/obj.strikeouts, 3)

            result = {
                "avg": avg,
                "slg": slg,
                "obp": obp,
                "ops": ops,
                "bb/k": bbk,
                "isop": isop,
                "total_raa": obj.total_raa,  # RAA 데이터 추가
            }

            return result
        else: return {}

    def get_raa_data(self, obj):
        """RAA (Runs Above Average) 데이터 반환"""
        try:
            return {
                "total_raa": obj.total_raa,
                "total_raa_percentile": obj.total_raa_percentile,                
                "offensive_raa": obj.offensive_raa,
                "offensive_raa_percentile": obj.offensive_raa_percentile,                
                "defensive_raa": obj.defensive_raa,
                "defensive_raa_percentile": obj.defensive_raa_percentile,                
                "batting_raa": obj.batting_raa,
                "batting_raa_percentile": obj.batting_raa_percentile,                
                "baserunning_raa": obj.baserunning_raa,
                "baserunning_raa_percentile": obj.baserunning_raa_percentile,                
                "fielding_raa": obj.fielding_raa,
                "fielding_raa_percentile": obj.fielding_raa_percentile,                
            }
        except:
            return {
                "total_raa": None,
                "total_raa_percentile": None,                
                "offensive_raa": None,
                "offensive_raa_percentile": None,                
                "defensive_raa": None,
                "defensive_raa_percentile": None,                
                "batting_raa": None,
                "batting_raa_percentile": None,                
                "baserunning_raa": None,
                "baserunning_raa_percentile": None,                
                "fielding_raa": None,
                "fielding_raa_percentile": None, 
            }

    class Meta:
        model = Batter
        fields = '__all__'

class PitcherSimpleSerializer(serializers.ModelSerializer):
    player = PlayerSerializer(read_only=True)
    stats = serializers.SerializerMethodField()

    def get_stats(self, obj):
        pa = obj.pa or 0

        if pa:
            inn = obj.innings
            k = obj.strikeouts

            return {
                "inn": inn,
                "k": k
            }
        else: return {
            "inn": 0.0,
            "k": 0
        }    

    class Meta:
        model = Pitcher
        fields = ['player', 'stats']

class BatterSimpleSerializer(serializers.ModelSerializer):
    player = PlayerSerializer(read_only=True)
    stats = serializers.SerializerMethodField()

    def get_stats(self, obj):
        ab = obj.ab or 0
        pa = obj.pa or 0
        hits = (obj.singles or 0) + (obj.doubles or 0) + (obj.triples or 0) + (obj.homeruns or 0)

        if pa:
            avg = round(hits / ab, 3) if ab else 0.0
            slg = round(
                ((obj.singles or 0) +
                2 * (obj.doubles or 0) +
                3 * (obj.triples or 0) +
                4 * (obj.homeruns or 0)) / ab, 3
            ) if ab else 0.0

            obp = round((hits + (obj.walks or 0)) / pa, 3) if pa else 0.0

            ops = round(obp + slg, 3)

            return {
                "avg": avg,
                "ops": ops,
            }
        else: return {
            "avg": 0.0,
            "ops": 0.0
        }

    class Meta:
        model = Batter
        fields = ['player', 'stats']