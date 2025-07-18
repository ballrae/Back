from ballrae_backend.games.models import AtBat, Player
from ballrae_backend.players.models import Batter, Pitcher
from django.db import transaction

@transaction.atomic
def create_players_from_atbats():
    batters = set()
    pitchers = set()

    atbats = AtBat.objects.select_related("inning__game").all()

    for ab in atbats:
        if not ab.inning or not ab.inning.game:
            continue  # 예외 데이터는 스킵

        half = ab.inning.half
        game = ab.inning.game

        if half == "top":
            batter_team = game.away_team
            pitcher_team = game.home_team
        elif half == "bot":
            batter_team = game.home_team
            pitcher_team = game.away_team

        # 타자 처리
        if ab.actual_player and ab.actual_player not in batters:
            player, _ = Player.objects.get_or_create(
                player_name=ab.actual_player,
                defaults={"position": "B", "team_id": batter_team}
            )
            if player.position != "B":
                player.position = "B"
                player.team_id = batter_team
                player.save()
            Batter.objects.get_or_create(player=player)
            batters.add(ab.actual_player)

        # 투수 처리
        if ab.pitcher and ab.pitcher not in pitchers:
            player, _ = Player.objects.get_or_create(
                player_name=ab.pitcher,
                defaults={"position": "P", "team_id": pitcher_team}
            )
            if player.position != "P":
                player.position = "P"
                player.team_id = pitcher_team
                player.save()
            Pitcher.objects.get_or_create(player=player)
            pitchers.add(ab.pitcher)

    print(f"✅ 등록 완료: 타자 {len(batters)}명 / 투수 {len(pitchers)}명")