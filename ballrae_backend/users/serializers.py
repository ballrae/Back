# users/serializers.py
from rest_framework import serializers
from .models import User
from ballrae_backend.teams.models import Team # 반드시 import 해야 함

class TeamUpdateSerializer(serializers.ModelSerializer):
    team_id = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all())

    class Meta:
        model = User
        fields = ['team_id']