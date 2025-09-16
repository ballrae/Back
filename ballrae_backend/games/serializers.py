# games/serializers.py
from rest_framework import serializers
from .models import Game, Inning, Player, PlayerTeamHistory, AtBat, Pitch

class PitchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pitch
        fields = '__all__'

class SimplePlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = ['id', 'player_name']

class AtBatSerializer(serializers.ModelSerializer):
    pitches = PitchSerializer(many=True, read_only=True)
    actual_player = serializers.SerializerMethodField()
    original_player = serializers.SerializerMethodField()
    pitcher = serializers.SerializerMethodField()

    class Meta:
        model = AtBat
        fields = '__all__'

    def get_actual_player(self, obj):
        if not obj.actual_player:
            return None
        player = Player.objects.filter(pcode=obj.actual_player).first()
        return {
            "id": player.id,
            "pcode": player.pcode,
            "player_name": player.player_name,
            "team_id": player.team_id
        }

    def get_original_player(self, obj):
        if not obj.original_player:
            return None
        player = Player.objects.filter(pcode=obj.original_player).first()
        return {
            "id": player.id,
            "pcode": player.pcode,
            "player_name": player.player_name,
            "team_id": player.team_id
        }

    def get_pitcher(self, obj):
        if not obj.pitcher:
            return None
        player = Player.objects.filter(pcode=obj.pitcher).first()
        return {
            "id": player.id,
            "pcode": player.pcode,
            "player_name": player.player_name,
            "team_id": player.team_id
        }


class InningSerializer(serializers.ModelSerializer):
    atbats = AtBatSerializer(many=True, read_only=True)

    class Meta:
        model = Inning
        fields = '__all__'

class GameSerializer(serializers.ModelSerializer):
    innings = InningSerializer(many=True, read_only=True)

    class Meta:
        model = Game
        fields = '__all__'

class GameDateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = ['id', 'status', 'dh', 'score', 'date', 'home_team', 'away_team']

class PlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = ['id', 'player_name', 'team_id', 'position']

class GamePlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = '__all__'
