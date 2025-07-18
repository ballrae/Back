# games/serializers.py
from rest_framework import serializers
from .models import Game, Inning, Player, PlayerTeamHistory, AtBat, Pitch

class PitchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pitch
        fields = '__all__'

class AtBatSerializer(serializers.ModelSerializer):
    pitches = PitchSerializer(many=True, read_only=True)

    class Meta:
        model = AtBat
        fields = '__all__'

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