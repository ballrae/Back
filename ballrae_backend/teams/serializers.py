# ballrae_backend/teams/serializers.py

from rest_framework import serializers
from .models import Team

class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team

        fields = '__all__'  # 모델의 모든 필드 + 아래 get 메서드 결과 포함

    total_games = serializers.SerializerMethodField()
    win_percentage = serializers.SerializerMethodField()

    def get_total_games(self, obj):
        return obj.total_games

    def get_win_percentage(self, obj):
        return obj.win_percentage