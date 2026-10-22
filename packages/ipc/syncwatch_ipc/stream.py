"""Bounded incremental framing and exactly-once command admission."""

from collections import OrderedDict
import copy

from .contracts import ContractError


class Frames:
    def __init__(self, limit=65536):
        self.limit = limit
        self.buffer = bytearray()

    def feed(self, data):
        # Consume incrementally: a large read containing many small frames
        # never creates an oversized retained partial frame.
        for byte in data:
            self.buffer.append(byte)
            if len(self.buffer) > self.limit:
                raise ContractError("frameTooLarge")
            if byte == 10:
                frame = bytes(self.buffer)
                self.buffer.clear()
                yield frame

    def eof(self):
        if self.buffer:
            raise ContractError("malformed")


class Replay:
    def __init__(self, capacity=128, pending_limit=64):
        self.capacity = capacity
        self.pending_limit = pending_limit
        self.high = 0
        self.pending = {}
        self.completed = OrderedDict()

    def admit(self, command):
        number = int(command["id"][4:])
        for collection in (self.pending, self.completed):
            if number in collection:
                original, result = collection[number]
                if original != command:
                    raise ContractError("conflict")
                return False, copy.deepcopy(result)
        if number <= self.high:
            raise ContractError("duplicate")
        if len(self.pending) >= self.pending_limit:
            raise ContractError("queueFull")
        self.high = number
        self.pending[number] = (copy.deepcopy(command), None)
        return True, None

    def complete(self, command, result):
        number = int(command["id"][4:])
        original, _ = self.pending.pop(number)
        self.completed[number] = (original, copy.deepcopy(result))
        while len(self.completed) > self.capacity:
            self.completed.popitem(last=False)
