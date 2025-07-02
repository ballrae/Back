from django.db import transaction
from .models import Game, Inning, Player, AtBat, Pitch

@transaction.atomic
def save_at_bat_transactionally(data: dict):
    game_data = data['game_id']
    atbat_data = data['at_bats']

    # 1. Game
    game, _ = Game.objects.get_or_create(id=game_data['id'], defaults=game_data)

    # 2. Inning
    inning, _ = Inning.objects.get_or_create(
        game=game,
        inning_number=data['inning'],
        defaults={'half': data.get('half', 'top')}
    )

    # # 3. Player
    # actual_player, _ = Player.objects.get_or_create(
    #     player_name=player_data['player_name'],
    #     defaults=player_data
    # )

    # 4. AtBat
    at_bats = atbat_data.get('at_bats', [])
    for atbat in at_bats:
        # actual_player는 atbat_data 내에서 actual_player로 처리한다고 가정
        actual_player = Player.objects.get(id=atbat['actual_player'])  # 예시로 Player를 가져오는 코드
        
        pitches_data = Player.objects.get(id=atbat['pitch_sequence'])

        # AtBat 생성
        at_bat = AtBat.objects.create(
            inning=inning,
            bat_order=atbat.get('bat_order'),
            result=atbat.get('result'),
            actual_player=actual_player,
            appearance_num=atbat.get('appearance_num', 1)
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