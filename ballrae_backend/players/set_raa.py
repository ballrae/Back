import os
import sys
import django
import pandas as pd
from django.db import transaction

# Django 설정
sys.path.append('/Users/yubin/Desktop/2025/dev/Back')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ballrae_backend.settings')
django.setup()

from ballrae_backend.players.models import Batter
from ballrae_backend.games.models import Player

def load_raa_data():
    """RAA 데이터를 로드하고 Batter 모델에 업데이트하는 함수"""
    
    # CSV 파일 경로
    csv_path = './data/raa_data.csv'
    
    # CSV 데이터 읽기
    df = pd.read_csv(csv_path)
    
    # 플레이어별로 RAA 데이터 그룹화
    player_raa_data = {}
    
    for _, row in df.iterrows():
        player_name = row['player_name']
        stat_type = row['스탯 종류']
        raa_value = row['RAA 값']
        rank = row['리그 순위']
        percentile = row['순위 퍼센티지 (%)']
        
        if player_name not in player_raa_data:
            player_raa_data[player_name] = {}
        
        # 스탯 종류에 따라 적절한 필드에 매핑
        if stat_type == '종합RAA':
            player_raa_data[player_name]['total_raa'] = raa_value
            player_raa_data[player_name]['total_raa_percentile'] = int(percentile)
        elif stat_type == '공격RAA':
            player_raa_data[player_name]['offensive_raa'] = raa_value
            player_raa_data[player_name]['offensive_raa_percentile'] = int(percentile)
        elif stat_type == '수비RAA':
            player_raa_data[player_name]['defensive_raa'] = raa_value
            player_raa_data[player_name]['defensive_raa_percentile'] = int(percentile)
        elif stat_type == '타격RAA':
            player_raa_data[player_name]['batting_raa'] = raa_value
            player_raa_data[player_name]['batting_raa_percentile'] = int(percentile)
        elif stat_type == '주루RAA':
            player_raa_data[player_name]['baserunning_raa'] = raa_value
            player_raa_data[player_name]['baserunning_raa_percentile'] = int(percentile)
        elif stat_type == '필딩RAA':
            player_raa_data[player_name]['fielding_raa'] = raa_value
            player_raa_data[player_name]['fielding_raa_percentile'] = int(percentile)
    
    # 데이터베이스 업데이트
    updated_count = 0
    not_found_players = []
    
    with transaction.atomic():
        for player_name, raa_data in player_raa_data.items():
            try:
                # Player 모델에서 이름으로 찾기
                player = Player.objects.get(player_name=player_name)
                
                batter = Batter.objects.filter(player=player, season=2025).first()
                
                if batter:
                    # RAA 데이터 업데이트
                    for field, value in raa_data.items():
                        setattr(batter, field, value)
                    
                    batter.save()
                    updated_count += 1
                    print(f"✅ {player_name}의 RAA 데이터 업데이트 완료")
                else:
                    print(f"⚠️ {player_name}의 Batter 인스턴스를 찾을 수 없습니다.")
                    
            except Player.DoesNotExist:
                not_found_players.append(player_name)
                print(f"❌ {player_name} 플레이어를 찾을 수 없습니다.")
            except Exception as e:
                print(f"❌ {player_name} 업데이트 중 오류 발생: {e}")
    
    print(f"\n📊 업데이트 완료:")
    print(f"   - 성공적으로 업데이트된 플레이어: {updated_count}명")
    print(f"   - 찾을 수 없는 플레이어: {len(not_found_players)}명")
    
    if not_found_players:
        print(f"   - 찾을 수 없는 플레이어 목록: {not_found_players}")

if __name__ == "__main__":
    load_raa_data()
