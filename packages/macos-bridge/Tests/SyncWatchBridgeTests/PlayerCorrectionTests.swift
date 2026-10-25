import Foundation
import SyncWatchDomain
import Testing

@testable import SyncWatchBridge

@Test func sharedHelperPlayerFrames() throws {
    let path = try #require(ProcessInfo.processInfo.environment["SYNCWATCH_CONTRACT_FIXTURES"])
    let url = URL(filePath: path).deletingLastPathComponent().appendingPathComponent("helper-player.json")
    let corpus = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    let scope = try PlaybackScope(clientRunID: "helper-run", mediaGeneration: 7)
    let cases = try #require(corpus["cases"] as? [[String: Any]])
    #expect(cases.count == 49)
    for fixture in cases {
        let bytes = fixture["hex"] == nil ? Data((fixture["frame"] as! String).utf8) : Data([255, 10])
        var accepted = false
        do {
            let command = try PlayerCorrection.decode(bytes, wireScope: scope)
            #expect(command.id == "cmd-9")
            #expect(command.afterUserAction == (fixture["name"] as? String == "legacy-zero-watermark" ? 0 : 3))
            accepted = true
        } catch {}
        #expect(accepted == fixture["accepted"] as? Bool, "\(fixture["name"] ?? "")")
    }
    let fixture = try #require(cases.first { $0["name"] as? String == "player.setPosition" })
    let command = try PlayerCorrection.decode(Data((fixture["frame"] as! String).utf8), wireScope: scope)
    let raw = fixture["frame"] as! String
    #expect(throws: (any Error).self) {
        try PlayerCorrection.decode(Data([239, 187, 191]) + Data(raw.utf8), wireScope: scope)
    }
    #expect(throws: (any Error).self) {
        try PlayerCorrection.decode(
            Data(raw.replacingOccurrences(of: "cmd-9", with: "cmd-9\\n").utf8), wireScope: scope)
    }
    let native = try PlaybackScope(clientRunID: "native-owner", mediaGeneration: 2)
    let actual = try PlaybackObservation(
        scope: native, sequence: 9, status: .ready, positionMs: 1300, durationMs: 4000, paused: true, rate: 1,
        seekable: true, buffering: false, ended: false, width: 0, height: 0, videoOutputs: 0, volume: nil, muted: false)
    let result = try #require(
        JSONSerialization.jsonObject(with: command.result(actual, nativeScope: native)) as? [String: Any])
    #expect(result["clientRunId"] as? String == scope.clientRunID)
    #expect(result["replyTo"] as? String == "cmd-9")
    #expect((result["payload"] as? [String: Any])?["positionMs"] as? Int64 == 1300)
    #expect(throws: (any Error).self) { try command.result(actual, nativeScope: scope) }
}
