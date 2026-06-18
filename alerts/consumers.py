import json
from channels.generic.websocket import AsyncWebsocketConsumer


class AlertConsumer(AsyncWebsocketConsumer):
    GROUP_NAME = 'alerts'
    ADMIN_GROUP_NAME = 'system_alerts'

    async def connect(self):
        await self.channel_layer.group_add(self.GROUP_NAME, self.channel_name)

        # 슈퍼관리자/관리자만 system_alerts 그룹 추가 구독
        user = self.scope.get('user')
        if user and user.is_authenticated and getattr(user, 'user_type', '') in ('admin', 'manager'):
            await self.channel_layer.group_add(self.ADMIN_GROUP_NAME, self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.GROUP_NAME, self.channel_name)
        await self.channel_layer.group_discard(self.ADMIN_GROUP_NAME, self.channel_name)

    async def alert_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'alert',
            'data': event['data'],
        }))

    async def system_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'system',
            'data': event['data'],
        }))
