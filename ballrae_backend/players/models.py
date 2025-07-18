# players/models.py

from django.db import models
from ballrae_backend.games.models import Player, Game  # 이미 정의된 모델들 import

class Batter(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    hits = models.IntegerField(default=0, null=True)
    at_bats = models.IntegerField(default=0, null=True)
    walks = models.IntegerField(default=0, null=True)
    strikeouts = models.IntegerField(default=0, null=True)
    home_runs = models.IntegerField(default=0, null=True)
    doubles = models.IntegerField(default=0, null=True)
    triples = models.IntegerField(default=0, null=True)
    player_name = models.CharField(max_length=20, null=True)   
    
    # 자동 계산 항목은 메서드로 제공
    @property
    def avg(self):
        return self.hits / self.at_bats if self.at_bats else 0

    @property
    def obp(self):
        pa = self.at_bats + self.walks  # 희생타 제외
        return (self.hits + self.walks) / pa if pa else 0

    @property
    def slg(self):
        total_bases = (self.hits - self.doubles - self.triples - self.home_runs) + \
                      (2 * self.doubles) + (3 * self.triples) + (4 * self.home_runs)
        return total_bases / self.at_bats if self.at_bats else 0

    @property
    def ops(self):
        return self.obp + self.slg
    
    def save(self, *args, **kwargs):
        if self.player:
            self.player_name = self.player.player_name  # 자동 복사
        super().save(*args, **kwargs)
    
class Pitcher(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, null=True)
    innings_pitched = models.FloatField(default=0.0, null=True)
    earned_runs = models.IntegerField(default=0, null=True)
    strikeouts = models.IntegerField(default=0, null=True)
    walks = models.IntegerField(default=0, null=True)
    player_name = models.CharField(max_length=20, null=True)   

    @property
    def era(self):
        return (self.earned_runs * 9) / self.innings_pitched if self.innings_pitched else 0