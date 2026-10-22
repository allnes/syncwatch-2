"""Publish headless engine observations without importing upstream GUI code."""

from syncplay.constants import CONSOLE_UI_MODE


class BridgeUI:
    uiMode = CONSOLE_UI_MODE

    def __init__(self, events):
        self.events = events

    def showMessage(self, message, noTimestamp=False, isMotd=False):
        self.events("sync.notice", {"message": message, "motd": isMotd})

    def showErrorMessage(self, message, criticalerror=False):
        self.events("sync.error", {"message": message, "critical": criticalerror})

    def setSSLMode(self, enabled, information=""):
        self.events("sync.tls", {"enabled": bool(enabled)})

    def setFeatures(self, features):
        self.events("sync.features", dict(features))

    def showUserList(self, current, rooms):
        users = [{"name": user.username, "room": room, "ready": user.isReady(),
                  "current": user is current} for room, values in rooms.items() for user in values]
        self.events("sync.participants", {"users": users})

    def userListChange(self):
        self.events("sync.participants.changed", {})

    def markEndOfUserlist(self):
        self.events("sync.participants.complete", {})

    def updateRoomName(self, room=""):
        self.events("sync.room", {"room": room})

    def addRoomToList(self, room):
        self.events("sync.room.discovered", {"room": room})

    def setPlaylist(self, playlist, newIndexFilename=None):
        self.events("sync.playlist", {"items": list(playlist), "selected": newIndexFilename})

    def addFileToPlaylist(self, item):
        self.events("sync.playlist.added", {"name": item})

    def setPlaylistIndexFilename(self, filename):
        self.events("sync.playlist.selected", {"name": filename})

    def fileSwitchFoundFiles(self):
        self.events("sync.media.changed", {})

    def updateAutoPlayState(self, state):
        self.events("sync.autoplay", {"enabled": state})

    def setControllerStatus(self, username, controller):
        self.events("sync.controller", {"name": username, "controller": controller})

    def executeCommand(self, command):
        self.events("sync.unsupported", {"operation": "interactive_command"})

    def promptFor(self, prompt):
        self.events("sync.unsupported", {"operation": "interactive_prompt"})

    def drop(self):
        self.events("sync.stopped", {})
