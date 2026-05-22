import json
from channels.generic.websocket import AsyncWebsocketConsumer


class AlertConsumer(AsyncWebsocketConsumer):
    GROUP_NAME = 'alerts'

    async def connect(self):
        await self.channel_layer.group_add(self.GROUP_NAME, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.GROUP_NAME, self.channel_name)

    async def alert_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'alert',
            'data': event['data'],
        }))
