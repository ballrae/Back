from django.db import transaction
from .models import Game, Inning, Player, AtBat, Pitch

@transaction.atomic
def save_at_bat_transactionally(data: dict):
    game_data = data['game']
    inning_data = data['inning']
    player_data = data['player']
    atbat_data = data['atbat']
    pitches_data = data['pitches']

    # 1. Game
    game, _ = Game.objects.get_or_create(id=game_data['id'], defaults=game_data)

    # 2. Inning
    inning, _ = Inning.objects.get_or_create(
        game=game,
        inning_number=inning_data['inning_number'],
        defaults={'half': inning_data.get('half', 'top')}
    )

    # 3. Player
    actual_player, _ = Player.objects.get_or_create(
        player_name=player_data['player_name'],
        defaults=player_data
    )

    # 4. AtBat
    at_bat = AtBat.objects.create(
        inning=inning,
        bat_order=atbat_data.get('bat_order'),
        result=atbat_data.get('result'),
        actual_player=actual_player,
        appearance_num=atbat_data.get('appearance_num', 1)
    )

    # 5. Pitches
    pitch_objs = []
    for pitch in pitches_data:
        pitch_objs.append(Pitch(
            at_bats=at_bat,
            pitch_num=pitch['pitch_num'],
            pitch_type=pitch['pitch_type'],
            speed=pitch['speed'],
            count=pitch['count'],
            pitch_result=pitch['pitch_result']
        ))
    Pitch.objects.bulk_create(pitch_objs)