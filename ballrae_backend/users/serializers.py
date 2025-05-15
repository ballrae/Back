# users/serializers.py

from rest_framework import serializers
from .models import User

class TeamUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['team_id']