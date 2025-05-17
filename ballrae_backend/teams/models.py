from django.db import models


class Team(models.Model):
    id = models.CharField(max_length=5, primary_key=True)  # 예: 'HH', 'LG' 등
    team_name = models.CharField(max_length=100, null=True, blank=True)
    team_logo = models.CharField(max_length=255, null=True, blank=True)  # URL 링크
    field = models.CharField(max_length=100, null=True, blank=True)  # 홈구장

    def __str__(self):
        return self.team_name