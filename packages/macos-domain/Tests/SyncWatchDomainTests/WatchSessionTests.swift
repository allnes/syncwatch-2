import Foundation
import Testing

@testable import SyncWatchDomain

private func corpus() throws -> [String: Any] {
    let path = try #require(ProcessInfo.processInfo.environment["SYNCWATCH_CONTRACT_FIXTURES"])
    let url = URL(fileURLWithPath: path).deletingLastPathComponent().appendingPathComponent("local-domain.json")
    let result = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    #expect(result["formatVersion"] as? Int == 1)
    return result
}

private func temporaryDirectory() throws -> URL {
    let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
}

private func describe(_ effect: WatchEffect) -> String {
    switch effect {
    case .load(let request):
        return
            "load:\(request.scope.clientRunID):\(request.scope.mediaGeneration):\(request.mediaID):\(request.positionMs)"
    case .release(let owner): return "release:\(owner.clientRunID):\(owner.mediaGeneration)"
    }
}

@Test func sharedLocalStateFormats() throws {
    let fixtures = try #require(corpus()["localStateCases"] as? [[String: Any]])
    #expect(fixtures.count == 31)
    let directory = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: directory) }
    let store = FileLocalStateStore(url: directory.appendingPathComponent("state.json"))
    #expect(try store.read() == .missing)
    for fixture in fixtures {
        let data: Data
        if let raw = fixture["json"] as? String {
            data = Data(raw.utf8)
        } else {
            data = try JSONSerialization.data(withJSONObject: #require(fixture["value"]), options: [.fragmentsAllowed])
        }
        try data.write(to: store.url)
        let result = try store.read()
        let status: String
        switch result {
        case .missing: status = "missing"
        case .invalid: status = "invalid"
        case .unsupportedVersion: status = "unsupportedVersion"
        case .loaded(let state):
            status = "loaded"
            #expect(state == (try JSONDecoder().decode(LocalState.self, from: data)))
        }
        #expect(status == fixture["status"] as? String, "Fixture: \(fixture["name"]!)")
    }
}

@Test func sharedWatchLifecycle() throws {
    let fixtures = try #require(corpus()["lifecycleCases"] as? [[String: Any]])
    #expect(fixtures.count == 6)
    for fixture in fixtures {
        var session = try WatchSession(
            scope: PlaybackScope(clientRunID: "run-1", mediaGeneration: fixture["initialGeneration"] as? UInt64 ?? 0)
        )
        let steps = try #require(fixture["steps"] as? [[String: Any]])
        for step in steps {
            let before = session
            var effects: [WatchEffect] = []
            var errorCode: String?
            let owner = try PlaybackScope(
                clientRunID: step["ownerRunId"] as? String ?? session.scope.clientRunID,
                mediaGeneration: step["ownerGeneration"] as? UInt64 ?? session.scope.mediaGeneration
            )
            do {
                switch step["op"] as? String {
                case "select": effects = try session.select(#require(step["mediaId"] as? String))
                case "start": effects = try session.start()
                case "loaded": try session.loaded(owner)
                case "observe":
                    try session.recordPlayback(
                        owner, positionMs: #require(step["positionMs"] as? Int64),
                        durationMs: step["durationMs"] as? Int64, paused: step["paused"] as? Bool ?? true
                    )
                case "home": session.returnToLibrary()
                case "continue": try session.continueWatching()
                case "end": effects = try session.end()
                case "cancel": effects = try session.cancel(owner)
                case "preferences":
                    var preferences = session.localState.preferences
                    preferences.movieVolume = try #require(step["movieVolume"] as? Double)
                    preferences.callVolume = try #require(step["callVolume"] as? Double)
                    try session.setPreferences(preferences)
                case "restart":
                    session = try WatchSession(
                        localState: session.localState, scope: PlaybackScope(clientRunID: "run-2", mediaGeneration: 0)
                    )
                default: Issue.record("Unknown fixture operation")
                }
            } catch let error as ContractRejection {
                errorCode = error.rawValue
            } catch let error as WatchError { errorCode = error.rawValue }
            #expect(errorCode == step["error"] as? String, "Fixture: \(fixture["name"]!) / \(step["op"]!)")
            if errorCode != nil {
                #expect(session.localState == before.localState)
                #expect(session.scope == before.scope)
                #expect(session.mediaID == before.mediaID)
            }
            let expected = try #require(step["expected"] as? [String: Any])
            #expect(session.phase.rawValue == expected["phase"] as? String)
            #expect(session.scope.mediaGeneration == expected["generation"] as? UInt64)
            #expect(session.positionMs == expected["positionMs"] as? Int64)
            #expect(session.paused == expected["paused"] as? Bool)
            #expect(session.playerPresented == expected["playerPresented"] as? Bool)
            #expect(effects.map(describe) == expected["effects"] as? [String])
        }
    }
}

@Test func persistenceRoundTripAndFailedWritesPreserveState() throws {
    let directory = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: directory) }
    let store = FileLocalStateStore(url: directory.appendingPathComponent("nested/state.json"))
    var session = try WatchSession()
    _ = try session.select("movie-a")
    _ = try session.start()
    try session.loaded(session.scope)
    try session.recordPlayback(session.scope, positionMs: 12345, durationMs: 50000, paused: true)
    var preferences = LocalPreferences()
    preferences.movieVolume = 0.25
    preferences.callVolume = 0
    preferences.cameraEnabled = false
    try session.setPreferences(preferences)
    try store.write(session.localState)
    let data = try Data(contentsOf: store.url)
    guard case .loaded(let restored) = try store.read() else {
        Issue.record("Saved state could not be read")
        return
    }
    let restarted = try WatchSession(localState: restored)
    #expect(restarted.scope.clientRunID != session.scope.clientRunID)
    #expect(restarted.phase == .selected && !restarted.playerPresented && restarted.paused)
    #expect(restarted.positionMs == 12345 && restarted.localState.preferences == preferences)
    var invalid = restored
    invalid.preferences.movieVolume = .nan
    #expect(throws: WatchError.invalidLocalState) { try store.write(invalid) }
    #expect(try Data(contentsOf: store.url) == data)
    #expect(
        try FileManager.default.contentsOfDirectory(atPath: store.url.deletingLastPathComponent().path) == [
            "state.json"
        ])
    // An OS-level failure must leave an existing destination intact.
    let destination = directory.appendingPathComponent("occupied")
    try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
    let sentinel = destination.appendingPathComponent("keep")
    try Data("unchanged".utf8).write(to: sentinel)
    #expect(throws: (any Error).self) { try FileLocalStateStore(url: destination).write(restored) }
    #expect(try Data(contentsOf: sentinel) == Data("unchanged".utf8))
}

@Test func corruptOversizedAndFutureFilesAreRecoverable() throws {
    let directory = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: directory) }
    let store = FileLocalStateStore(url: directory.appendingPathComponent("state.json"))
    for bytes in [Data("{".utf8), Data(repeating: 32, count: FileLocalStateStore.maximumBytes + 1)] {
        try bytes.write(to: store.url)
        #expect(try store.read() == .invalid)
        #expect(try Data(contentsOf: store.url) == bytes)
    }
    let future = Data("{\"version\":2,\"futureSetting\":true}".utf8)
    try future.write(to: store.url)
    #expect(try store.read() == .unsupportedVersion)
    #expect(throws: WatchError.unsupportedVersion) { try store.write(LocalState()) }
    #expect(try Data(contentsOf: store.url) == future)
}

@Test func resumeHistoryIsBoundedAndKeepsRecentUpdates() throws {
    var session = try WatchSession()
    for index in 0...256 {
        _ = try session.select("movie-\(index)")
        _ = try session.start()
        try session.loaded(session.scope)
        try session.recordPlayback(session.scope, positionMs: Int64(index + 1), durationMs: nil, paused: true)
    }
    #expect(session.localState.resumePositions.count == 256)
    #expect(session.localState.resumePosition(for: "movie-0") == 0)
    #expect(session.localState.resumePosition(for: "movie-256") == 257)
    try session.recordPlayback(session.scope, positionMs: 500, durationMs: nil, paused: true)
    #expect(session.localState.resumePositions.count == 256)
    #expect(session.localState.resumePositions.last?.positionMs == 500)
    _ = try session.select("movie-1")
    _ = try session.start()
    try session.loaded(session.scope)
    try session.recordPlayback(session.scope, positionMs: 900, durationMs: nil, paused: true)
    _ = try session.select("movie-257")
    _ = try session.start()
    try session.loaded(session.scope)
    try session.recordPlayback(session.scope, positionMs: 1, durationMs: nil, paused: true)
    #expect(session.localState.resumePosition(for: "movie-1") == 900)
    #expect(session.localState.resumePosition(for: "movie-2") == 0)
    var invalid = session.localState
    invalid.resumePositions.append(ResumePosition(mediaID: "extra", positionMs: 1))
    #expect(throws: WatchError.invalidLocalState) { try invalid.validate() }
}

@Test func playlistSelectionRestartsOnlyTheChosenFileAndFencesOldObservations() throws {
    var session = try WatchSession()
    for (id, position) in [("first", Int64(12000)), ("second", Int64(24000))] {
        _ = try session.select(id)
        _ = try session.start()
        try session.loaded(session.scope)
        try session.recordPlayback(session.scope, positionMs: position, durationMs: 60000, paused: true)
    }
    let old = session.scope
    #expect(try session.select("second").isEmpty)
    let release = try session.select("second", restartFromBeginning: true)
    #expect(release == [.release(old)])
    #expect(session.positionMs == 0 && session.localState.resumePosition(for: "second") == 0)
    #expect(session.localState.resumePosition(for: "first") == 12000)
    #expect(session.scope != old && session.phase == .selected)
    #expect(throws: (any Error).self) {
        try session.recordPlayback(old, positionMs: 50000, durationMs: 60000, paused: false)
    }
    guard case .load(let load) = try #require(session.start().first) else {
        Issue.record("Missing playlist load")
        return
    }
    #expect(load.positionMs == 0 && load.scope == session.scope)
    try session.loaded(session.scope)
    _ = try session.select("first")
    #expect(session.positionMs == 12000)
}
