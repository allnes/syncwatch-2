import Foundation
import Testing

@testable import SyncWatchDomain

@Test func sharedNativeActionOrderingCases() throws {
    let path = try #require(ProcessInfo.processInfo.environment["SYNCWATCH_CONTRACT_FIXTURES"])
    let url = URL(fileURLWithPath: path).deletingLastPathComponent().appendingPathComponent("playback-authority.json")
    let corpus = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    let initial = try #require(corpus["scope"] as? [String: Any])
    let scope = try PlaybackScope(
        clientRunID: #require(initial["clientRunId"] as? String),
        mediaGeneration: #require(initial["mediaGeneration"] as? UInt64))
    let cases = try #require(corpus["cases"] as? [[String: Any]])
    #expect(cases.count == 5)
    for fixture in cases {
        var fence = PlaybackActionFence(scope: scope)
        for step in try #require(fixture["steps"] as? [[String: Any]]) {
            let owner = try PlaybackScope(
                clientRunID: step["ownerRunId"] as? String ?? scope.clientRunID,
                mediaGeneration: step["ownerGeneration"] as? UInt64 ?? scope.mediaGeneration)
            let before = fence
            var result = ""
            var errorCode: String?
            do {
                switch step["op"] as? String {
                case "begin": result = String(try fence.beginUserAction(owner))
                case "canPublish":
                    result = String(try fence.canPublish(#require(step["sequence"] as? UInt64), owner: owner))
                case "publish":
                    let status = step["status"] as? String == "loading" ? PlaybackStatus.loading : .ready
                    let observation = try PlaybackObservation(
                        scope: owner, sequence: 0, status: status, positionMs: 0,
                        durationMs: status == .ready ? 4000 : nil, paused: true, rate: 1,
                        seekable: status == .ready, buffering: false, ended: false,
                        width: 0, height: 0, videoOutputs: 0, volume: nil, muted: false)
                    result = String(
                        try fence.didPublish(#require(step["sequence"] as? UInt64), observation: observation))
                case "correction":
                    result = try fence.correction(owner, afterUserAction: #require(step["afterUserAction"] as? UInt64))
                        .rawValue
                case "invalidate": fence.invalidate()
                default: Issue.record("Unknown authority fixture")
                }
            } catch let error as ContractRejection { errorCode = error.rawValue } catch let error as WatchError {
                errorCode = error.rawValue
            }
            #expect(errorCode == step["error"] as? String, "\(fixture["name"] ?? "") \(step)")
            if errorCode == nil {
                #expect(result == (step["result"] as? String ?? ""))
            } else {
                #expect(fence.issuedSequence == before.issuedSequence)
                #expect(fence.publishedSequence == before.publishedSequence)
                #expect(fence.invalidated == before.invalidated)
            }
        }
    }
}
