from django.db import models
import datetime

class Game(models.Model):
    id = models.CharField(max_length=50, primary_key=True, )  # 날짜+away+home+dh
    status = models.CharField(max_length=20, default='scheduled')
    dh = models.IntegerField(default=0)
    score = models.CharField(max_length=10, null=True)
    date = models.DateTimeField(null=False, default=datetime.datetime(1970, 1, 1, 0, 0))
    home_team = models.CharField(max_length=5)
    away_team = models.CharField(max_length=5)

class Inning(models.Model):
    game = models.ForeignKey(Game, related_name='innings', on_delete=models.CASCADE)
    inning_number = models.IntegerField()
    half = models.CharField(max_length=5, null=True)  # top / bot

class Player(models.Model):
    player_name = models.CharField(max_length=20)
    position = models.CharField(max_length=10, null=True)
    # player_code = models.CharField(max_length=10, null=True)
    team_id = models.CharField(max_length=5)
    player_bdate = models.DateField(null=True)

class PlayerTeamHistory(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    start_year = models.CharField(max_length=5, null=True)
    end_year = models.CharField(max_length=5, null=True)
    is_current_team = models.BooleanField(default=False)
    team_id = models.CharField(max_length=5)
    move_index = models.IntegerField(default=0)

class AtBat(models.Model):
    inning = models.ForeignKey(Inning, related_name='atbats', on_delete=models.CASCADE)
    pitcher = models.CharField(max_length=5, null=True)
    bat_order = models.IntegerField(null=True)
    out = models.CharField(max_length=3, null=True)
    score = models.CharField(max_length=6, null=True)
    on_base = models.CharField(max_length=50, null=True)
    full_result = models.CharField(max_length=255, null=True)
    strike_zone = models.CharField(max_length=255, null=True)
    original_player = models.CharField(max_length=20, null=True)
    actual_player = models.CharField(max_length=20, null=False, default='타자')
    appearance_num = models.IntegerField(default=1)
    main_result = models.CharField(max_length=255, null=True)

class Pitch(models.Model):
    at_bats = models.ForeignKey(AtBat, related_name='pitches', on_delete=models.CASCADE)
    pitch_num = models.IntegerField(null=True)
    pitch_type = models.CharField(max_length=50, null=True)
    speed = models.FloatField(null=True)
    count = models.CharField(max_length=10, null=True)
    pitch_coordinate = models.JSONField(null=True) 
    pitch_result = models.CharField(max_length=255, null=True)
    event = models.CharField(max_length=255, null=True)