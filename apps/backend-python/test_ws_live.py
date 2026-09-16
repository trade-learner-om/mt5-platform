import unittest
from unittest.mock import AsyncMock

from app.services.ws_live import WS_LIVE_HEARTBEAT_SECONDS, handle_live_socket_message


class WsLiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_ping_payload_receives_pong(self):
        websocket = AsyncMock()
        handled = await handle_live_socket_message(AsyncMock(), "user-1", websocket, '{"type":"ping"}', AsyncMock())
        self.assertTrue(handled)
        websocket.send_json.assert_awaited_once_with({"type": "pong"})

    async def test_plain_ping_receives_pong(self):
        websocket = AsyncMock()
        handled = await handle_live_socket_message(AsyncMock(), "user-1", websocket, "ping", AsyncMock())
        self.assertTrue(handled)
        websocket.send_json.assert_awaited_once_with({"type": "pong"})

    async def test_pong_is_ignored(self):
        websocket = AsyncMock()
        handled = await handle_live_socket_message(AsyncMock(), "user-1", websocket, '{"type":"pong"}', AsyncMock())
        self.assertTrue(handled)
        websocket.send_json.assert_not_awaited()

    def test_heartbeat_interval_is_twenty_seconds(self):
        self.assertEqual(WS_LIVE_HEARTBEAT_SECONDS, 20)


if __name__ == "__main__":
    unittest.main()
