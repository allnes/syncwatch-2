from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "packages/ipc"), str(ROOT / "packages/syncplay-helper")]
from syncwatch_bridge.engine import Engine, PlayerPort


class EnginePortTests(unittest.TestCase):
    def setUp(self):
        self.events, self.observed, self.requests = [], [], []
        controller = SimpleNamespace(event=lambda k, p: self.events.append((k, p)))
        self.engine = Engine(controller)
        self.engine.port = PlayerPort(controller)
        self.engine.port.request_state(lambda paused, position: self.observed.append((paused, position)))
        self.engine.media = {"durationMs": 60000}
        self.state = {"status": "ready", "durationMs": 60000, "positionMs": 1200,
                      "paused": False, "rate": 1, "seekable": True}
        user = SimpleNamespace(username="player-a", room="room", isReady=lambda: False)
        self.engine.session = SimpleNamespace(_protocol=None, has_initial_state=True,
            userlist=SimpleNamespace(currentUser=user, _users={}),
            changeReadyState=self.requests.append)

    def test_disconnected_observation_is_retained_without_calling_protocol(self):
        self.engine.observe(self.state)
        self.assertEqual(self.observed, [])
        self.assertEqual(self.engine.port.state, self.state)
        self.engine.session._protocol = SimpleNamespace(logged=True)
        self.engine.observe(self.state)
        self.assertEqual(self.observed, [(False, 1200)])

    def test_correction_result_cannot_become_another_observation(self):
        self.engine.port.state = dict(self.state)
        self.engine.player_result({"status": "applied", "positionMs": 0, "paused": True})
        self.assertEqual(self.observed, [])
        self.assertEqual(self.engine.port.state, self.state)

    def test_readiness_request_does_not_publish_optimistic_state(self):
        self.engine.port.state = dict(self.state)
        self.engine.ready(True)
        self.assertEqual(self.requests, [True])
        self.assertEqual(self.events, [])
        self.engine.tick()
        self.assertIn(("sync.readiness", {"ready": False}), self.events)
        self.engine.session.userlist.currentUser.isReady = lambda: True
        self.engine.tick()
        self.assertEqual(self.events[-2], ("sync.readiness", {"ready": True}))

    def test_released_native_port_cannot_publish_again(self):
        self.engine.port.release()
        self.engine.session._protocol = SimpleNamespace(logged=True)
        self.engine.observe(self.state)
        self.assertEqual(self.observed, [])


if __name__ == "__main__":
    unittest.main()
