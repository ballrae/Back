from django.db import models


class Team(models.Model):
    id = models.CharField(max_length=5, primary_key=True)  # 예: 'HH', 'LG' 등
    team_name = models.CharField(max_length=100, null=True, blank=True)
    team_logo = models.CharField(max_length=255, null=True, blank=True)  # URL 링크
    field = models.CharField(max_length=100, null=True, blank=True)  # 홈구장

    # 순위와 연승/연패 계산을 위한 필드 추가
    wins = models.IntegerField(default=0, null=True)
    loses = models.IntegerField(default=0, null=True)
    tie = models.IntegerField(default=0, null=True)
    consecutive_streak = models.IntegerField(default=0, null=True)

    @property
    def total_games(self):
        # total_games는 wins + loses + tie의 합
        return (self.wins or 0) + (self.loses or 0) + (self.tie or 0)

    @property
    def win_percentage(self):
        # 승률(영어로 win_percentage)은 wins / (wins + loses)
        total = (self.wins or 0) + (self.loses or 0)
        if total == 0:
            return 0.0
        return round((self.wins or 0) / total, 3)

    def __str__(self):
        return self.team_name