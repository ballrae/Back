# # games/management/commands/kafka_relay.py

# from kafka import KafkaConsumer
# from django.core.management.base import BaseCommand
# from asgiref.sync import async_to_sync
# from channels.layers import get_channel_layer
# import json
# import time

# class Command(BaseCommand):
#     help = 'Kafka consumer that pushes data to WebSocket clients'

#     print("🚀 Kafka consumer starting...")
    
#     def handle(self, *args, **options):
#         consumer = KafkaConsumer(
#             '2025',
#             bootstrap_servers='kafka:9092',
#             auto_offset_reset='latest',
#             group_id='ws-relay-group',
#             enable_auto_commit=True,
#             value_deserializer=lambda x: json.loads(x.decode('utf-8')),
#         )

#         channel_layer = get_channel_layer()

#         for message in consumer:
#             data = message.value
#             game_id = data.get('game_id')
#             group_name = f"relay_{game_id}"

#             # WebSocket 그룹으로 브로드캐스트
#             async_to_sync(channel_layer.group_send)(
#                 group_name,
#                 {
#                     'type': f'send_relay_data : {game_id}',
#                     'data': data
#                 }
#             )
#             print(f"📤 중계 → {group_name}: {data}")
#             time.sleep(0.1)