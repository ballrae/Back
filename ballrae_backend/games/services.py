from django.db import transaction
from .models import Game, Inning, Player, AtBat, Pitch
import json
from django.db.models import Q

@transaction.atomic
def save_at_bat_transactionally(data: dict):
    print(data)
    game_id = data['game_id']
    atbat_data = data['at_bats']

    game, _ = Game.objects.get_or_create(id=game_id)

    inning, _ = Inning.objects.get_or_create(
        game=game,
        inning_number=data['inning'],
        defaults={'half': data.get('half', 'top')}
    )

    for atbat in atbat_data:
        # 중복 체크
        exists = AtBat.objects.filter(
            inning=inning,
            actual_player=atbat.get('actual_batter'),
            appearance_num=atbat.get('appearance_num', 1)
        ).exists()

        if exists:
            print(f"이미 저장된 타석: {atbat.get('actual_batter')} #{atbat.get('appearance_num')}")
            continue

        # 새 타석 저장
        at_bat = AtBat.objects.create(
            inning=inning,
            bat_order=atbat.get('bat_order'),
            pitcher=atbat.get('pitcher'),
            main_result=atbat.get('main_result'),
            full_result=atbat.get('full_result'),
            original_player=atbat.get('original_batter'),
            actual_player=atbat.get('actual_batter'),
            appearance_num=atbat.get('appearance_num', 1)
        )

        pitches_data = atbat.get("pitch_sequence", [])
        for pitch in pitches_data:
            Pitch.objects.get_or_create(
                at_bats=at_bat,
                pitch_num=pitch['pitch_num'],
                pitch_type=pitch.get('pitch_type'),
                speed=pitch.get('speed'),
                count=pitch.get('count'),
                pitch_coordinate=pitch.get('pitch_coordinate'),
                event=pitch.get('event'),
                pitch_result=pitch.get('pitch_result')
            )
