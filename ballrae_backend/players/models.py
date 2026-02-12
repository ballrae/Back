# players/models.py

from django.db import models
from ballrae_backend.games.models import Player, Game  # 이미 정의된 모델들 import

class Batter(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    season = models.IntegerField(null=True, blank=True)  # None이면 통산 기록

    games = models.IntegerField(default=0, null=True)   # 경기수
    pa = models.IntegerField(default=0, null=True)  # 타석
    ab = models.IntegerField(default=0, null=True)  # 타수
    walks = models.IntegerField(default=0, null=True)   # 볼넷/사구/고의4구
    strikeouts = models.IntegerField(default=0, null=True)  # 삼진
    homeruns = models.IntegerField(default=0, null=True)   # 홈런
    singles = models.IntegerField(default=0, null=True)     # 단타 (1루타)
    doubles = models.IntegerField(default=0, null=True)     # 2루타
    triples = models.IntegerField(default=0, null=True)     # 3루타
    war = models.FloatField(default=0.0, null=True)
    wrc = models.FloatField(default=0.0, null=True)
    babip = models.FloatField(default=0.0, null=True)
    
    # RAA (Runs Above Average) 필드들
    total_raa = models.FloatField(default=0.0, null=True)  # 종합RAA
    offensive_raa = models.FloatField(default=0.0, null=True)  # 공격RAA
    defensive_raa = models.FloatField(default=0.0, null=True)  # 수비RAA
    batting_raa = models.FloatField(default=0.0, null=True)  # 타격RAA
    baserunning_raa = models.FloatField(default=0.0, null=True)  # 주루RAA
    fielding_raa = models.FloatField(default=0.0, null=True)  # 필딩RAA
    
    # RAA 순위 정보
    total_raa_percentile = models.IntegerField(null=True, blank=True)
    offensive_raa_percentile = models.IntegerField(null=True, blank=True)
    defensive_raa_percentile = models.IntegerField(null=True, blank=True)
    batting_raa_percentile = models.IntegerField(null=True, blank=True)
    baserunning_raa_percentile = models.IntegerField(null=True, blank=True)
    fielding_raa_percentile = models.IntegerField(null=True, blank=True)

    @property
    def name(self):
        return self.player.player_name
    
class Pitcher(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, null=True)
    season = models.IntegerField(null=True, blank=True)  # None이면 통산 기록

    games = models.IntegerField(default=0)   # 경기수
    pa = models.IntegerField(default=0, null=True)  # 피타석    
    ab = models.IntegerField(default=0, null=True)  # 피타수
    innings = models.FloatField(default=0.0, null=True)
    walks = models.IntegerField(default=0, null=True)
    strikeouts = models.IntegerField(default=0, null=True)  # 탈삼진
    homeruns = models.IntegerField(default=0, null=True)   # 피홈런
    singles = models.IntegerField(default=0, null=True)     # 피단타 (1루타)
    doubles = models.IntegerField(default=0, null=True)     # 피2루타
    triples = models.IntegerField(default=0, null=True)     # 피3루타
    era = models.FloatField(default=0.0, null=True)
    war = models.FloatField(default=0.0, null=True)
    w = models.IntegerField(default=0, null=True) 
    l = models.IntegerField(default=0, null=True) 
    sv = models.IntegerField(default=0, null=True)

    @property
    def name(self):
        return self.player.player_name

class BatterRecent(models.Model):
    batter = models.OneToOneField(Batter, on_delete=models.CASCADE)
    ab = models.IntegerField(default=0)      # 누적 타수
    hits = models.IntegerField(default=0)    # 누적 안타수
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def avg(self):
        return round(self.hits / self.ab, 3) if self.ab else 0.0