# games/serializers.py
from rest_framework import serializers
from .models import Game, Inning, Player, PlayerTeamHistory, AtBat, Pitch

class GameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = ['id', 'status', 'dh', 'score', 'date', 'home_team', 'away_team']

# Inning 모델 직렬화
class InningSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inning
        fields = ['game', 'inning_number', 'half']

# Player 모델 직렬화
class PlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = ['player_name', 'position', 'player_code', 'team_id', 'player_bdate']

# PlayerTeamHistory 모델 직렬화
class PlayerTeamHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlayerTeamHistory
        fields = ['player', 'start_year', 'end_year', 'is_current_team', 'team_id', 'move_index']

# AtBat 모델 직렬화
class AtBatSerializer(serializers.ModelSerializer):
    original_player = PlayerSerializer(read_only=True)  # original_player는 PlayerSerializer로 직렬화
    actual_player = PlayerSerializer(read_only=True)    # actual_player도 PlayerSerializer로 직렬화

    class Meta:
        model = AtBat
        fields = ['inning', 'bat_order', 'result', 'original_player', 'actual_player', 'appearance_num']

# Pitch 모델 직렬화
class PitchSerializer(serializers.ModelSerializer):
    at_bats = AtBatSerializer(read_only=True)  # at_bats는 AtBatSerializer로 직렬화

    class Meta:
        model = Pitch
        fields = ['at_bats', 'pitch_num', 'pitch_type', 'speed', 'count', 'pitch_coordinate', 'pitch_result', 'event']