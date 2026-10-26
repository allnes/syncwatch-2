import Foundation

final class RoomSessionDelegate: NSObject, URLSessionWebSocketDelegate {
    let termination = RoomSocketTermination()

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        guard task is URLSessionWebSocketTask else { return }
        termination.finish()
    }
    func urlSession(
        _ session: URLSession, webSocketTask: URLSessionWebSocketTask,
        didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?
    ) {
        termination.finish()
    }

    func urlSession(
        _ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void
    ) {
        completionHandler(nil)
    }
}

/// One room attempt owns all network work; close cancels and joins it before credentials are released.
public actor RoomClient {
    public let address: RoomAddress
    private let session: URLSession
    private let eventSession: URLSession
    private let delegate: RoomSessionDelegate
    private var requests: [UUID: Task<Data, Error>] = [:]
    private var closed = false
    private var eventStream: RoomEventStream?
    public init(address: RoomAddress) {
        self.address = address
        let configuration = Self.configuration()
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 20
        let delegate = RoomSessionDelegate()
        self.delegate = delegate
        session = URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
        // A live event stream must not inherit the short whole-response HTTP deadline.
        // Bootstrap is bounded by the controller; the SDK retains its normal stream limits.
        eventSession = URLSession(configuration: Self.configuration(), delegate: delegate, delegateQueue: nil)
    }
    private static func configuration() -> URLSessionConfiguration {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpShouldSetCookies = false
        configuration.httpCookieStorage = nil
        configuration.urlCredentialStorage = nil
        configuration.urlCache = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.httpMaximumConnectionsPerHost = 2
        return configuration
    }

    public func create(identity: RoomIdentity, connection: RoomConnection, creationKey: RoomSecret) async throws
        -> RoomAdmission
    {
        let body = try RoomWire.encode([
            "v": 1, "clientRunId": identity.clientRunID, "syncplayUsername": identity.syncplayUsername,
            "syncplayHost": connection.host, "syncplayPort": connection.port, "syncplayRoom": connection.room,
        ])
        return try RoomAdmission.decode(
            await request("POST", "v1/rooms", credential: creationKey, body: body), identity: identity, owner: true)
    }
    public func join(roomID: String, invitation: RoomSecret, identity: RoomIdentity) async throws -> RoomAdmission {
        try RoomWire.id(roomID)
        let body = try RoomWire.encode([
            "v": 1, "invitation": invitation.value, "clientRunId": identity.clientRunID,
            "syncplayUsername": identity.syncplayUsername,
        ])
        return try RoomAdmission.decode(
            await request("POST", "v1/rooms/\(roomID)/join", body: body), identity: identity, owner: false)
    }
    public func snapshot(_ admission: RoomAdmission) async throws -> RoomBootstrap {
        try RoomBootstrap.decode(
            await request("GET", "v1/rooms/\(admission.roomID)/snapshot", credential: admission.token))
    }
    public func catalog(_ admission: RoomAdmission, bootstrap: RoomBootstrap, cursor: String) async throws
        -> RoomCatalogPage
    {
        guard bootstrap.snapshot.epoch == admission.bootstrap.snapshot.epoch else {
            throw RoomProtocolFailure.malformed
        }
        _ = try RoomCatalogPosition(cursor, bootstrap: bootstrap)
        return try RoomCatalogPage.decode(
            await request("GET", "v1/rooms/\(admission.roomID)/catalog", credential: admission.token, cursor: cursor),
            bootstrap: bootstrap, cursor: cursor)
    }
    /// The caller serializes bootstrap creation with this walk and bounds its overall lifetime.
    public func catalogView(_ admission: RoomAdmission, bootstrap: RoomBootstrap) async throws -> RoomCatalogView {
        guard bootstrap.snapshot.epoch == admission.bootstrap.snapshot.epoch else {
            throw RoomProtocolFailure.malformed
        }
        return try await RoomCatalogView.read(bootstrap: bootstrap) { cursor in
            try await self.request(
                "GET", "v1/rooms/\(admission.roomID)/catalog", credential: admission.token, cursor: cursor)
        }
    }
    public func leave(_ admission: RoomAdmission) async throws {
        let bytes = try await request("POST", "v1/rooms/\(admission.roomID)/leave", credential: admission.token)
        let value = try RoomWire.object(bytes)
        try RoomWire.keys(value, ["v", "status"])
        guard try RoomWire.integer(value["v"], maximum: 1) == 1, value["status"] as? String == "left" else {
            throw RoomProtocolFailure.malformed
        }
    }
    public func execute(_ admission: RoomAdmission, command: RoomCommand) async throws -> RoomCommandResult {
        try command.verify(admission)
        return try RoomCommandResult.decode(
            await request(
                "POST", "v1/rooms/\(admission.roomID)/commands", credential: admission.token, body: command.encodedBytes
            ),
            command: command)
    }
    /// Attach immediately after admission, before hashing media or performing other long work.
    public func openEvents(_ admission: RoomAdmission) async throws -> RoomEventStream {
        try Task.checkCancellation()
        guard !closed, eventStream == nil else { throw RoomProtocolFailure.closed }
        var parts = URLComponents(
            url: address.endpoint("v1/rooms/\(admission.roomID)/events"), resolvingAgainstBaseURL: false)!
        parts.scheme = address.origin.scheme == "https" ? "wss" : "ws"
        var request = URLRequest(url: parts.url!)
        request.setValue("Bearer \(admission.token.value)", forHTTPHeaderField: "Authorization")
        let stream = RoomEventStream(socket: eventSession.webSocketTask(with: request))
        eventStream = stream
        delegate.termination.bind(stream)
        await stream.start()
        guard !closed else {
            await stream.close()
            throw RoomProtocolFailure.closed
        }
        return stream
    }
    public func close() async {
        closed = true
        let pending = Array(requests.values)
        for task in pending { task.cancel() }
        session.invalidateAndCancel()
        eventSession.invalidateAndCancel()
        if let eventStream { await eventStream.close() }
        for task in pending { _ = await task.result }
    }
    private func request(
        _ method: String, _ path: String, credential: RoomSecret? = nil, body: Data? = nil, cursor: String? = nil
    )
        async throws -> Data
    {
        try Task.checkCancellation()
        guard !closed else { throw RoomProtocolFailure.closed }
        var parts = URLComponents(url: address.endpoint(path), resolvingAgainstBaseURL: false)!
        if let cursor { parts.queryItems = [URLQueryItem(name: "cursor", value: cursor)] }
        var request = URLRequest(url: parts.url!)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let credential { request.setValue("Bearer \(credential.value)", forHTTPHeaderField: "Authorization") }
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let id = UUID()
        let session = session
        let task = Task { try await Self.transfer(session, request: request) }
        requests[id] = task
        defer { requests.removeValue(forKey: id) }
        let data = try await withTaskCancellationHandler(
            operation: { try await task.value }, onCancel: { task.cancel() })
        try Task.checkCancellation()
        guard !closed else { throw RoomProtocolFailure.closed }
        return data
    }
    private static func transfer(_ session: URLSession, request: URLRequest) async throws -> Data {
        let (stream, response) = try await session.bytes(for: request)
        defer { stream.task.cancel() }
        guard let response = response as? HTTPURLResponse, response.url == request.url,
            response.mimeType?.lowercased() == "application/json"
        else { throw RoomProtocolFailure.transport }
        guard response.expectedContentLength <= RoomWire.maximumBytes else { throw RoomProtocolFailure.frameTooLarge }
        var data = Data()
        for try await byte in stream {
            try Task.checkCancellation()
            guard data.count < RoomWire.maximumBytes else { throw RoomProtocolFailure.frameTooLarge }
            data.append(byte)
        }
        guard (200...299).contains(response.statusCode) else {
            // Never publish server text, headers or echoed request credentials as an error.
            let value = try RoomWire.object(data)
            try RoomWire.keys(value, ["error"])
            let error = try RoomWire.dictionary(value["error"])
            try RoomWire.keys(error, ["code"])
            let code = try RoomWire.string(error["code"])
            let allowed = [
                "unauthorized", "forbidden", "notFound", "conflict", "expired", "queueFull", "tlsRequired", "malformed",
                "frameTooLarge", "internal", "snapshotRequired", "duplicate",
            ]
            throw RoomProtocolFailure.rejected(allowed.contains(code) ? code : "transport")
        }
        return data
    }
}
