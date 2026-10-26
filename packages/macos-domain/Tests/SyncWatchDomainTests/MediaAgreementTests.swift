import Foundation
import Testing

@testable import SyncWatchDomain

private struct AgreementCorpus: Decodable {
    struct Descriptor: Decodable {
        let mediaId: String
        let title: String
        let titleKey: String
        let fileSizeBytes: Int64
        let durationMs: Int64?
        let fullHashSha256: String?
        func value() throws -> MediaDescriptor {
            try MediaDescriptor(
                mediaID: mediaId, title: title, titleKey: titleKey, fileSizeBytes: fileSizeBytes,
                durationMs: durationMs, fullHashSha256: fullHashSha256)
        }
    }
    struct Normalization: Decodable {
        let title: String
        let key: String
    }
    struct Case: Decodable {
        let name: String
        let remote: String
        let local: [String]
        let status: String?
        let candidateIds: [String]
        let error: String?
    }
    struct Validation: Decodable {
        let name: String
        let value: Descriptor
        let error: String?
    }
    let normalization: [Normalization]
    let descriptors: [String: Descriptor]
    let cases: [Case]
    let validation: [Validation]
}

@Test func sharedMediaAgreementCorpus() throws {
    let fixtures = try #require(ProcessInfo.processInfo.environment["SYNCWATCH_CONTRACT_FIXTURES"])
    let path = URL(fileURLWithPath: fixtures).deletingLastPathComponent().appendingPathComponent("media-agreement.json")
    let corpus = try JSONDecoder().decode(AgreementCorpus.self, from: Data(contentsOf: path))
    for item in corpus.normalization { #expect(MediaDescriptor.normalizedTitleKey(item.title) == item.key) }
    for fixture in corpus.validation {
        var error: String?
        do { _ = try fixture.value.value() } catch let failure as ContractRejection { error = failure.rawValue }
        #expect(error == fixture.error, "\(fixture.name)")
    }
    for fixture in corpus.cases {
        let remote = try #require(corpus.descriptors[fixture.remote]).value()
        let local = try fixture.local.map { try #require(corpus.descriptors[$0]).value() }
        var error: String?
        do {
            let result = try MediaAgreement.resolve(remote, local: local)
            #expect(result.status.rawValue == fixture.status, "\(fixture.name)")
            #expect(result.candidateIDs == fixture.candidateIds, "\(fixture.name)")
        } catch let failure as ContractRejection { error = failure.rawValue }
        #expect(error == fixture.error, "\(fixture.name)")
    }
    let remote = try #require(corpus.descriptors["remote"]).value()
    let excessive = try (0...256).map {
        try MediaDescriptor(
            mediaID: "local-\($0)", title: remote.title, titleKey: remote.titleKey,
            fileSizeBytes: remote.fileSizeBytes, durationMs: remote.durationMs, fullHashSha256: nil)
    }
    #expect(throws: ContractRejection.malformed) { try MediaAgreement.resolve(remote, local: excessive) }
}
