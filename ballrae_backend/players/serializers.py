# players/serializers.py
from rest_framework import serializers
from .models import Batter, Pitcher
from ballrae_backend.games.serializers import PlayerSerializer

class PitcherSerializer(serializers.ModelSerializer):
    player = PlayerSerializer(read_only=True)

    class Meta:
        model = Pitcher
        fields = '__all__'

class BatterSerializer(serializers.ModelSerializer):
    player = PlayerSerializer(read_only=True)

    class Meta:
        model = Batter
        fields = '__all__'