import json
from channels.generic.websocket import AsyncWebsocketConsumer


class WorkerConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.floor_id   = self.scope['url_route']['kwargs']['floor_id']
        self.group_name = f'floor_{self.floor_id}_worker'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def worker_update(self, event):
        await self.send(text_data=json.dumps({
            'type': event['msg_type'],
            'data': event['data'],
        }))


class SensorConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.floor_id   = self.scope['url_route']['kwargs']['floor_id']
        self.group_name = f'floor_{self.floor_id}_sensor'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def sensor_update(self, event):
        await self.send(text_data=json.dumps({
            'type': event['msg_type'],
            'data': event['data'],
        }))


class GeofenceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.floor_id   = self.scope['url_route']['kwargs']['floor_id']
        self.group_name = f'floor_{self.floor_id}_geofence'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def geofence_update(self, event):
        await self.send(text_data=json.dumps({
            'type': event['msg_type'],
            'data': event['data'],
        }))


class ForecastConsumer(AsyncWebsocketConsumer):
    """AI 예측·판정 전용 (현재상태 SensorConsumer와 분리). store consumer가 저장 후 push."""
    async def connect(self):
        self.floor_id   = self.scope['url_route']['kwargs']['floor_id']
        self.group_name = f'floor_{self.floor_id}_forecast'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def forecast_update(self, event):
        await self.send(text_data=json.dumps({
            'type': event['msg_type'],
            'data': event['data'],
        }))