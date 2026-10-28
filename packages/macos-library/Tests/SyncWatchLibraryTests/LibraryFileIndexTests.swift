import Foundation
import Testing

@testable import SyncWatchLibrary

private struct CompanionCorpus: Decodable {
    struct Case: Decodable {
        struct Expected: Decodable {
            let video: String
            let folder: Bool
            let audio: [String]
            let subtitles: [String]
        }
        let id: String
        let caseSensitive: Bool
        let videos: [String]
        let audio: [String]
        let subtitles: [String]
        let expected: [Expected]
    }
    let cases: [Case]
    let invalidPaths: [String]
}

@Test func libraryCompanionCorpus() throws {
    let fixture = URL(fileURLWithPath: ProcessInfo.processInfo.environment["SYNCWATCH_LIBRARY_FIXTURE"]!)
        .deletingLastPathComponent().appendingPathComponent("library-companions.json")
    let corpus = try JSONDecoder().decode(CompanionCorpus.self, from: Data(contentsOf: fixture))
    for item in corpus.cases {
        for reversed in [false, true] {
            let index = try LibraryFileIndex(
                videos: reversed ? Array(item.videos.reversed()) : item.videos,
                audio: reversed ? Array(item.audio.reversed()) : item.audio,
                subtitles: reversed ? Array(item.subtitles.reversed()) : item.subtitles,
                caseSensitive: item.caseSensitive)
            for expected in item.expected {
                #expect(index.isFolderMovie(expected.video) == expected.folder, "\(item.id)")
                #expect(index.audioPaths(for: expected.video) == expected.audio, "\(item.id)")
                #expect(index.subtitlePaths(for: expected.video) == expected.subtitles, "\(item.id)")
            }
            let unknown =
                "not-in-snapshot/" + (item.videos.first?.split(separator: "/").last.map(String.init) ?? "film.mkv")
            #expect(!index.isFolderMovie(unknown))
            #expect(index.audioPaths(for: unknown).isEmpty)
            #expect(index.subtitlePaths(for: unknown).isEmpty)
        }
    }
    for path in corpus.invalidPaths {
        #expect(throws: CocoaError.self) {
            try LibraryFileIndex(videos: [path], audio: [], subtitles: [], caseSensitive: true)
        }
    }
}
