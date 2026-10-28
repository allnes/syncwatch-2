import Foundation
import Testing

@testable import SyncWatchLibrary

@Test func observedTrackNamesRetainOrderAndValueSemantics() throws {
    var names = ["English", "Русский"]
    let value = try MediaMetadata(
        durationMs: 1000, width: 320, height: 180, audioTracks: 2,
        subtitleTracks: 0, audioTrackNames: names, subtitleTrackNames: [])
    names[0] = "Changed"
    #expect(value.audioTrackNames == ["English", "Русский"] && value.subtitleTrackNames == [])
    #expect(
        value
            == (try MediaMetadata(
                durationMs: 1000, width: 320, height: 180, audioTracks: 2,
                subtitleTracks: 0, audioTrackNames: ["English", "Русский"], subtitleTrackNames: [])))
    #expect(
        try MediaMetadata(
            durationMs: nil, width: 0, height: 0, audioTracks: 2,
            subtitleTracks: 0
        ).audioTrackNames == nil)
}

@Test func observedTrackNamesRejectMismatchedCountsAndUnsafeLabels() {
    for names in [[], ["English", "Русский"], ["bad\0label"], [String(repeating: "é", count: 2049)]] {
        #expect(throws: MediaMetadataFailure.self) {
            try MediaMetadata(
                durationMs: nil, width: 0, height: 0, audioTracks: 1,
                subtitleTracks: 0, audioTrackNames: names, subtitleTrackNames: [])
        }
    }
    #expect(throws: MediaMetadataFailure.self) {
        try MediaMetadata(
            durationMs: nil, width: 0, height: 0, audioTracks: 0,
            subtitleTracks: 1, audioTrackNames: [], subtitleTrackNames: [])
    }
}

@Test func observedTrackNameBoundaryUsesUTF8Bytes() throws {
    let value = try MediaMetadata(
        durationMs: nil, width: 0, height: 0, audioTracks: 1,
        subtitleTracks: 0, audioTrackNames: [String(repeating: "é", count: 2048)], subtitleTrackNames: [])
    #expect(value.audioTrackNames?.first?.utf8.count == 4096)
}

@Test func rowDurationCacheIsBoundedAndVersionScoped() {
    func file(_ id: String, size: Int64 = 1) -> LocalMediaFile {
        LocalMediaFile(
            id: id, title: id, relativePath: id, file: URL(filePath: "/movies/" + id),
            sizeBytes: size, modificationDate: Date(timeIntervalSince1970: 10))
    }
    let a = file("a")
    let b = file("b")
    let c = file("c")
    var cache = LibraryDurationCache(capacity: 2)
    cache.record(60_000, for: a)
    cache.record(90_000, for: b)
    cache.record(120_000, for: c)
    #expect(cache.duration(for: a) == nil && cache.duration(for: b) == 90_000)
    #expect(cache.duration(for: file("b", size: 2)) == nil)
    cache.reconcile([file("b", size: 2), c])
    #expect(cache.duration(for: b) == nil && cache.duration(for: c) == 120_000)
    cache.reconcile([b])
    #expect(cache.duration(for: c) == nil)
    cache.record(60_000, for: b)
    cache.record(nil, for: b)
    #expect(cache.duration(for: b) == nil)
    cache.record(0, for: b)
    #expect(cache.duration(for: b) == nil)
    cache.record(60_000, for: b)
    cache.clear()
    #expect(cache.duration(for: b) == nil)
}
