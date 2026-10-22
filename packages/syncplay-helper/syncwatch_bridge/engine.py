"""Bind the pipe controller to the real upstream engine; no synchronization policy."""

from syncwatch_ipc.contracts import ContractError
from syncwatch_syncplay.session import Session


class PlayerPort:
    def __init__(self, controller):
        self.controller = controller
        self.observer = None
        self.state = None
        self.released = False

    def request_state(self, callback):
        self.observer = callback

    def observe(self, state):
        self.state = dict(state)
        if self.observer is not None and not self.released:
            self.observer(state["paused"], state["positionMs"])

    def set_paused(self, value):
        self.controller.request("player.setPaused", {"paused": value})

    def set_position(self, value):
        self.controller.request("player.setPosition", {"positionMs": value})

    def set_rate(self, value):
        self.controller.request("player.setSpeed", {"rate": value})

    def open_media(self, handle, reset):
        self.controller.request("player.openFile", {"mediaHandle": handle})
        if reset:
            self.set_position(0)

    def release(self):
        self.released = True
        self.observer = None


class Engine:
    def __init__(self, controller, *, trust_roots=None):
        self.controller, self.trust_roots = controller, trust_roots
        self.session = None
        self.port = None
        self.media = None
        self.status = None
        self.last_participants = None

    def connect(self, payload):
        if self.session is not None:
            raise ContractError("invalidState")
        self.port = PlayerPort(self.controller)
        self.session = Session(payload["host"], payload["port"], payload["username"], payload["room"],
                               self.port, self.event, trust_roots=self.trust_roots)
        if self.media is not None:
            self.apply_media()
        self.connection("connecting")
        self.session.connect()

    def event(self, kind, payload):
        # Raw upstream text may contain room/user/file data. It is never
        # forwarded to stderr or mistaken for a wire frame.
        if kind == "sync.disconnected":
            self.connection("disconnected")
            self.controller.event("sync.readiness", {"ready": False})

    def connection(self, state):
        if self.status != state:
            self.status = state
            self.controller.event("sync.connection", {"state": state})

    def loaded(self, payload):
        if self.media is not None:
            raise ContractError("invalidState")
        self.media = dict(payload)
        if self.session is not None:
            self.apply_media()

    def apply_media(self):
        m = self.media
        self.session.media_loaded(m["mediaHandle"], m["name"], m["durationMs"], m["fileSizeBytes"])

    def observe(self, state):
        if self.port is None or self.media is None:
            raise ContractError("invalidState")
        if state["durationMs"] != self.media["durationMs"]:
            raise ContractError("conflict")
        self.port.observe(state)

    def player_result(self, result):
        if self.port is None:
            raise ContractError("invalidState")
        if self.port.state is None:
            return
        state = self.port.state | {"positionMs": result["positionMs"], "paused": result["paused"]}
        self.port.observe(state)

    def ready(self, value):
        if (self.session is None or not self.session.has_initial_state or self.port.state is None
                or self.port.state["status"] != "ready"):
            raise ContractError("invalidState")
        self.session.changeReadyState(value)
        self.controller.event("sync.readiness", {"ready": self.session.userlist.currentUser.isReady() is True})

    def tick(self):
        session = self.session
        if session is None:
            return
        if session.has_initial_state:
            self.connection("connected")
        users = [session.userlist.currentUser, *session.userlist._users.values()]
        participants = [{"username": user.username, "ready": user.isReady() is True}
                        for user in users if user.room == session.userlist.currentUser.room]
        if len(participants) > 64:
            raise ContractError("queueFull")
        if participants != self.last_participants:
            self.last_participants = participants
            self.controller.event("sync.participants", {"participants": participants})

    def disconnect(self, done):
        session, self.session = self.session, None
        if session is None:
            done()
        else:
            session.close().addBoth(lambda _: done())
        self.connection("disconnected")

    def close(self, done):
        self.disconnect(done)
