import Testing
@testable import SyncWatchLibrary

@Test func observedTrackNamesRetainOrderAndValueSemantics() throws {
    var names = ["English", "Русский"]
    let value = try MediaMetadata(durationMs: 1000, width: 320, height: 180, audioTracks: 2,
        subtitleTracks: 0, audioTrackNames: names, subtitleTrackNames: [])
    names[0] = "Changed"
    #expect(value.audioTrackNames == ["English", "Русский"] && value.subtitleTrackNames == [])
    #expect(value == (try MediaMetadata(durationMs: 1000, width: 320, height: 180, audioTracks: 2,
        subtitleTracks: 0, audioTrackNames: ["English", "Русский"], subtitleTrackNames: [])))
    #expect(try MediaMetadata(durationMs: nil, width: 0, height: 0, audioTracks: 2,
        subtitleTracks: 0).audioTrackNames == nil)
}

@Test func observedTrackNamesRejectMismatchedCountsAndUnsafeLabels() {
    for names in [[], ["English", "Русский"], ["bad\0label"], [String(repeating: "é", count: 2049)]] {
        #expect(throws: MediaMetadataFailure.self) {
            try MediaMetadata(durationMs: nil, width: 0, height: 0, audioTracks: 1,
                subtitleTracks: 0, audioTrackNames: names, subtitleTrackNames: [])
        }
    }
    #expect(throws: MediaMetadataFailure.self) {
        try MediaMetadata(durationMs: nil, width: 0, height: 0, audioTracks: 0,
            subtitleTracks: 1, audioTrackNames: [], subtitleTrackNames: [])
    }
}

@Test func observedTrackNameBoundaryUsesUTF8Bytes() throws {
    let value = try MediaMetadata(durationMs: nil, width: 0, height: 0, audioTracks: 1,
        subtitleTracks: 0, audioTrackNames: [String(repeating: "é", count: 2048)], subtitleTrackNames: [])
    #expect(value.audioTrackNames?.first?.utf8.count == 4096)
}
