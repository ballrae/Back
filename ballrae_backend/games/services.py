from django.db import transaction
from .models import Game, Inning, Player, AtBat, Pitch
import json
from django.db.models import Q

@transaction.atomic
def save_at_bat_transactionally(data: dict, game_id):
    atbat_data = data['at_bats']

    game, _ = Game.objects.get_or_create(id=game_id)

    inning, _ = Inning.objects.get_or_create(
        game=game,
        inning_number=data['inning'],
        half=data.get('half', 'top')
    )

    for atbat in atbat_data:
        try:
            if inning.half == 'top': b_id = game_id[8:10]; p_id = game_id[10:12]
            else: b_id = game_id[10:12]; p_id = game_id[8:10]
            pitcher = atbat.get('pitcher', [])

            if pitcher:
                batter, _ = Player.objects.get_or_create(
                    # player_name=atbat.get('actual_batter'),
                    position='B',
                    team_id=b_id,
                    pcode=atbat.get('actual_batter')
                )

                pitcher, _ = Player.objects.get_or_create(
                    # player_name=atbat.get('pitcher'),
                    position='P',
                    team_id=p_id,
                    pcode=atbat.get('pitcher')
                )
        
            # 중복 체크
            exists = AtBat.objects.filter(
                inning=inning,
                actual_player=atbat.get('actual_batter'),
                bat_order=atbat.get('bat_order'),
                appearance_num=atbat.get('appearance_number', 1)
            ).exists()

            if exists:
                print(f"이미 저장된 타석: {atbat.get('actual_batter')} #{atbat.get('appearance_number')}")
                continue

            # 새 타석 저장
            at_bat = AtBat.objects.create(
                inning=inning,
                bat_order=atbat.get('bat_order'),
                pitcher=atbat.get('pitcher'),
                out=atbat.get('out'),
                score=atbat.get('score'),
                on_base=atbat.get('on_base'),
                strike_zone=atbat.get('strike_zone'),
                main_result=atbat.get('main_result'),
                full_result=atbat.get('full_result'),
                original_player=atbat.get('original_batter'),
                actual_player=atbat.get('actual_batter'),
                appearance_num=atbat.get('appearance_number', 1)
            )

            pitches_data = atbat.get("pitch_sequence", [])

            if pitches_data:
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
        except:
            print(game, inning, batter.player_name, "error")
            continue
