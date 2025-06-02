from django.contrib import admin
from .models import Game, Inning, AtBat, Pitch, Player, PlayerTeamHistory

admin.site.register(Game)
admin.site.register(Inning)
admin.site.register(AtBat)
admin.site.register(Pitch)
admin.site.register(Player)
admin.site.register(PlayerTeamHistory)