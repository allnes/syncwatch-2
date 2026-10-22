"""Actual upstream TLS server/clients with an explicitly simulated native player."""

import datetime
import ipaddress
import json
from pathlib import Path
import time
import threading

import syncwatch_syncplay
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from syncwatch_syncplay.reactor import install
reactor = install()
from twisted.internet import defer, protocol, task
from syncplay.server import SyncFactory
from syncplay.protocols import SyncServerProtocol
from syncwatch_syncplay.session import Session


class SimulatedPlayer:
    """A clocked state port, not VLC or a physical media acceptance test."""
    def __init__(self):
        self.paused = True
        self.position = 0
        self.rate = 1.0
        self.since = time.monotonic()
        self.commands = []
        self.released = False
        self.release_count = 0

    def current(self):
        return self.position if self.paused else self.position + round((time.monotonic() - self.since) * self.rate * 1000)

    def request_state(self, report):
        report(self.paused, self.current())

    def set_paused(self, value):
        self.position = self.current()
        self.since = time.monotonic()
        self.paused = value
        self.commands.append(("pause", value))

    def set_position(self, value):
        self.position = value
        self.since = time.monotonic()
        self.commands.append(("position", value))

    def set_rate(self, value):
        self.position = self.current()
        self.since = time.monotonic()
        self.rate = value
        self.commands.append(("rate", value))

    def open_media(self, handle, reset):
        self.commands.append(("open", handle))

    def release(self):
        self.released = True
        self.release_count += 1


class ObservedServerProtocol(SyncServerProtocol):
    def connectionMade(self):
        receive = self.transport._dataReceived
        def record(data):
            self._factory.wire.append(data)
            return receive(data)
        self.transport._dataReceived = record
        super().connectionMade()

    def handleHello(self, hello):
        self._factory.hellos.append(hello.get("username"))
        super().handleHello(hello)

    def handleState(self, state):
        self._factory.states.append(state)
        super().handleState(state)


class ObservedFactory(SyncFactory):
    def __init__(self, *args, **kwargs):
        self.hellos, self.states, self.wire = [], [], []
        super().__init__(*args, **kwargs)

    def buildProtocol(self, address):
        return ObservedServerProtocol(self)


def certificate_set(directory, root_key, root_certificate, *, bad_name=False, expired=False):
    directory.mkdir()
    now = datetime.datetime.now(datetime.timezone.utc)
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SyncWatch runtime fixture")])
    alternative = x509.DNSName("wrong.invalid") if bad_name else x509.IPAddress(ipaddress.ip_address("127.0.0.1"))
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(root_certificate.subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=2))
            .not_valid_after(now - datetime.timedelta(days=1) if expired else now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([alternative]), critical=False)
            .sign(root_key, hashes.SHA256()))
    (directory / "privkey.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    (directory / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (directory / "chain.pem").write_bytes(root_certificate.public_bytes(serialization.Encoding.PEM))


@defer.inlineCallbacks
def wait_for(predicate, description, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("Actual Syncplay acceptance timed out: " + description)
        yield task.deferLater(reactor, 0.02, lambda: None)
