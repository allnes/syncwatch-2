// SPDX-License-Identifier: Apache-2.0
// Generate first-party H.264/AAC media using the Apple platform encoder SDK.
// No camera, microphone, imported assets, external encoder or font is used.
import AVFoundation
import Foundation

enum FixtureError: Error { case failed(String) }
let width = Int(CommandLine.arguments.dropFirst(3).first ?? "320") ?? 0
let height = Int(CommandLine.arguments.dropFirst(4).first ?? "180") ?? 0
let codecName = CommandLine.arguments.dropFirst(2).first ?? "h264"
let codec: AVVideoCodecType = codecName == "hevc" ? .hevc : .h264
let fps = 25
let seconds = 4
let rate = 48000

final class FailureBox {
    private let lock = NSLock()
    private var value: Error?
    func store(_ error: Error) {
        lock.lock()
        defer { lock.unlock() }
        if value == nil { value = error }
    }
    func load() -> Error? {
        lock.lock()
        defer { lock.unlock() }
        return value
    }
}

final class TrackProgress {
    var frame = 0
    var finished = false
}

func require(_ value: Bool, _ message: String) throws {
    if !value { throw FixtureError.failed(message) }
}

func feed(
    _ input: AVAssetWriterInput, group: DispatchGroup, failures: FailureBox,
    append: @escaping (Int) throws -> Void
) {
    let progress = TrackProgress()
    group.enter()
    input.requestMediaDataWhenReady(on: DispatchQueue(label: "fixture." + input.mediaType.rawValue)) {
        guard !progress.finished else { return }
        do {
            while input.isReadyForMoreMediaData && progress.frame < fps * seconds {
                try append(progress.frame)
                progress.frame += 1
            }
            if progress.frame < fps * seconds { return }
        } catch { failures.store(error) }
        progress.finished = true
        input.markAsFinished()
        group.leave()
    }
}

func create(_ url: URL) throws {
    try require(!FileManager.default.fileExists(atPath: url.path), "Fixture destination already exists")
    let writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
    let video = AVAssetWriterInput(
        mediaType: .video,
        outputSettings: [
            AVVideoCodecKey: codec,
            AVVideoWidthKey: width, AVVideoHeightKey: height,
            AVVideoCompressionPropertiesKey: [
                AVVideoAverageBitRateKey: 200000,
                AVVideoMaxKeyFrameIntervalKey: fps, AVVideoAllowFrameReorderingKey: false,
            ],
        ])
    let pixels = AVAssetWriterInputPixelBufferAdaptor(
        assetWriterInput: video,
        sourcePixelBufferAttributes: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,
            kCVPixelBufferWidthKey as String: width, kCVPixelBufferHeightKey as String: height,
        ])
    let audio = AVAssetWriterInput(
        mediaType: .audio,
        outputSettings: [
            AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: rate,
            AVNumberOfChannelsKey: 2, AVEncoderBitRateKey: 128000,
        ])
    try require(writer.canAdd(video) && writer.canAdd(audio), "Platform encoders unavailable")
    writer.add(video)
    writer.add(audio)
    try require(writer.startWriting(), "Cannot start platform encoder")
    writer.startSession(atSourceTime: .zero)
    var description = AudioStreamBasicDescription(
        mSampleRate: Double(rate), mFormatID: kAudioFormatLinearPCM,
        mFormatFlags: kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked,
        mBytesPerPacket: 4, mFramesPerPacket: 1, mBytesPerFrame: 4, mChannelsPerFrame: 2,
        mBitsPerChannel: 16, mReserved: 0)
    var format: CMAudioFormatDescription?
    try require(
        CMAudioFormatDescriptionCreate(
            allocator: kCFAllocatorDefault, asbd: &description,
            layoutSize: 0, layout: nil, magicCookieSize: 0, magicCookie: nil, extensions: nil,
            formatDescriptionOut: &format) == noErr, "Cannot describe original PCM")
    let group = DispatchGroup()
    let failures = FailureBox()
    feed(video, group: group, failures: failures) { frame in
        var buffer: CVPixelBuffer?
        try require(
            CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, pixels.pixelBufferPool!, &buffer)
                == kCVReturnSuccess,
            "Cannot allocate fixture pixels")
        let pixelBuffer = buffer!
        CVPixelBufferLockBaseAddress(pixelBuffer, [])
        let base = CVPixelBufferGetBaseAddress(pixelBuffer)!.assumingMemoryBound(to: UInt8.self)
        let stride = CVPixelBufferGetBytesPerRow(pixelBuffer)
        for y in 0..<height {
            for x in 0..<width {
                let offset = y * stride + x * 4
                base[offset] = 255
                base[offset + 1] = UInt8(40 + frame * 2)
                base[offset + 2] = UInt8(40 + frame * 2)
                base[offset + 3] = UInt8(40 + frame * 2)
            }
        }
        CVPixelBufferUnlockBaseAddress(pixelBuffer, [])
        try require(
            pixels.append(pixelBuffer, withPresentationTime: CMTime(value: Int64(frame), timescale: Int32(fps))),
            "Cannot append fixture video")

    }
    feed(audio, group: group, failures: failures) { frame in
        var pcm = [Int16]()
        pcm.reserveCapacity(rate / fps * 2)
        for sample in 0..<(rate / fps) {
            let position = frame * (rate / fps) + sample
            let value = Int16((7000 * sin(2 * Double.pi * 440 * Double(position) / Double(rate))).rounded())
            pcm.append(value)
            pcm.append(value)
        }
        var block: CMBlockBuffer?
        let size = pcm.count * MemoryLayout<Int16>.size
        try require(
            CMBlockBufferCreateWithMemoryBlock(
                allocator: kCFAllocatorDefault, memoryBlock: nil,
                blockLength: size, blockAllocator: kCFAllocatorDefault, customBlockSource: nil,
                offsetToData: 0, dataLength: size, flags: 0, blockBufferOut: &block) == kCMBlockBufferNoErr,
            "Cannot allocate fixture audio")
        let copied = pcm.withUnsafeBytes { bytes in
            CMBlockBufferReplaceDataBytes(
                with: bytes.baseAddress!, blockBuffer: block!, offsetIntoDestination: 0, dataLength: size)
        }
        try require(copied == kCMBlockBufferNoErr, "Cannot copy fixture audio")
        var timing = CMSampleTimingInfo(
            duration: CMTime(value: 1, timescale: Int32(rate)),
            presentationTimeStamp: CMTime(value: Int64(frame * (rate / fps)), timescale: Int32(rate)),
            decodeTimeStamp: .invalid)
        var sampleSize = 4
        var sample: CMSampleBuffer?
        try require(
            CMSampleBufferCreateReady(
                allocator: kCFAllocatorDefault, dataBuffer: block,
                formatDescription: format, sampleCount: rate / fps, sampleTimingEntryCount: 1,
                sampleTimingArray: &timing, sampleSizeEntryCount: 1, sampleSizeArray: &sampleSize,
                sampleBufferOut: &sample) == noErr, "Cannot describe fixture audio")
        try require(audio.append(sample!), "Cannot append fixture audio")
    }
    try require(group.wait(timeout: .now() + 30) == .success, "Platform encoder tracks stalled")
    if let error = failures.load() {
        writer.cancelWriting()
        throw error
    }
    let finished = DispatchSemaphore(value: 0)
    writer.finishWriting { finished.signal() }
    try require(
        finished.wait(timeout: .now() + 30) == .success && writer.status == .completed,
        "Cannot finish fixture: \(String(describing: writer.error))")
}

do {
    try require(
        [2, 5].contains(CommandLine.arguments.count),
        "usage: create-encoded-fixture output.mp4 [h264|hevc width height]")
    try require(
        ["h264", "hevc"].contains(codecName) && width > 0 && width <= 4096 && height > 0 && height <= 2160
            && width % 2 == 0 && height % 2 == 0, "Invalid fixture codec or dimensions")
    try create(URL(fileURLWithPath: CommandLine.arguments[1]))
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}
