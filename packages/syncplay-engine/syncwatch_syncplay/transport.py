"""Authenticated STARTTLS with no cleartext Hello or downgrade path."""

from twisted.internet import reactor
from twisted.internet.ssl import Certificate, TLSVersion, optionsForClientTLS, trustRootFromCertificates
from syncplay.client import SyncClientFactory
from syncplay.protocols import SyncClientProtocol


def tls_options(hostname, certificates):
    if not certificates:
        raise ValueError("An explicit owned trust root is required")
    roots = trustRootFromCertificates([Certificate.loadPEM(value) for value in certificates])
    return optionsForClientTLS(hostname, trustRoot=roots,
        extraCertificateOptions={"raiseMinimumTo": TLSVersion.TLSv1_2})


class StrictClientProtocol(SyncClientProtocol):
    def __init__(self, client):
        super().__init__(client)
        self._phase = "new"
        self._deadline = None

    def connectionMade(self):
        self._client.initProtocol(self)
        self._phase = "requested"
        self.sendTLS({"startTLS": "send"})
        self._deadline = reactor.callLater(self._client.handshake_timeout, self._reject, "tls_timeout")

    def _cancel_deadline(self):
        if self._deadline is not None and self._deadline.active():
            self._deadline.cancel()

    def _reject(self, code):
        if self._phase == "failed":
            return
        self._phase = "failed"
        self._cancel_deadline()
        self._client.transport_failed(code)
        self.abort()

    def handleMessages(self, messages):
        if not isinstance(messages, dict):
            self._reject("malformed_syncplay_message")
        elif self._phase != "secured" and (self._phase != "requested" or set(messages) != {"TLS"}):
            self._reject("unauthenticated_syncplay_message")
        else:
            super().handleMessages(messages)

    def handleTLS(self, message):
        if self._phase != "requested" or not isinstance(message, dict) or message.get("startTLS") != "true":
            self._reject("tls_required")
            return
        self._phase = "handshaking"
        self.transport.startTLS(self._client.protocolFactory.options)

    def handshakeCompleted(self):
        if self._phase != "handshaking" or self.transport.getPeerCertificate() is None:
            self._reject("tls_certificate_missing")
            return
        # Twisted invokes this callback only after chain and service identity
        # verification by the explicit optionsForClientTLS context above.
        self._phase = "secured"
        self._cancel_deadline()
        super().handshakeCompleted()

    def sendHello(self):
        if self._phase != "secured":
            self._reject("cleartext_hello_forbidden")
            return
        super().sendHello()

    def connectionLost(self, reason):
        self._cancel_deadline()
        super().connectionLost(reason)
        self._client.transport_failed("connection_lost")


class StrictClientFactory(SyncClientFactory):
    def buildProtocol(self, address):
        self.options = self._client.tls_options
        if self.options is None:
            raise ValueError("Authenticated TLS context is required")
        return StrictClientProtocol(self._client)
