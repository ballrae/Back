# players/models.py

from django.db import models
from ballrae_backend.games.models import Player, Game  # 이미 정의된 모델들 import

class Batter(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    games = models.IntegerField(default=0, null=True)   # 경기수
    pa = models.IntegerField(default=0, null=True)  # 타수
    ab = models.IntegerField(default=0, null=True)  # 타석
    walks = models.IntegerField(default=0, null=True)   # 볼넷/사구/고의4구
    strikeouts = models.IntegerField(default=0, null=True)  # 삼진
    homeruns = models.IntegerField(default=0, null=True)   # 홈런
    singles = models.IntegerField(default=0, null=True)     # 단타 (1루타)
    doubles = models.IntegerField(default=0, null=True)     # 2루타
    triples = models.IntegerField(default=0, null=True)     # 3루타

    @property
    def name(self):
        return self.player.player_name
    
class Pitcher(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, null=True)
    games = models.IntegerField(default=0)   # 경기수
    pa = models.IntegerField(default=0, null=True)  # 피타수    
    innings = models.FloatField(default=0.0, null=True)
    walks = models.IntegerField(default=0, null=True)
    strikeouts = models.IntegerField(default=0, null=True)  # 탈삼진
    homeruns = models.IntegerField(default=0, null=True)   # 피홈런
    singles = models.IntegerField(default=0, null=True)     # 피단타 (1루타)
    doubles = models.IntegerField(default=0, null=True)     # 피2루타
    triples = models.IntegerField(default=0, null=True)     # 피3루타

    @property
    def name(self):
        return self.player.player_name