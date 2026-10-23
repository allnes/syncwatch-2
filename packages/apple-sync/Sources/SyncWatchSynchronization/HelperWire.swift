import CoreFoundation
import Foundation
import SyncWatchDomain

enum SessionFailure: Error { case malformed, order, unavailable, timeout, concurrentOwner, queueFull }

/// Value-only JSON data can cross actors; Foundation's untyped containers cannot.
indirect enum WireValue: Sendable, Equatable {
    case string(String)
    case number(Double)
    case flag(Bool)
    case object([String: WireValue])
    case array([WireValue])
    case null
    init(_ value: Any) throws {
        if let n = value as? NSNumber {
            self = CFGetTypeID(n) == CFBooleanGetTypeID() ? .flag(n.boolValue) : .number(n.doubleValue)
        } else if let s = value as? String {
            self = .string(s)
        } else if let d = value as? [String: Any] {
            self = .object(try d.mapValues(WireValue.init))
        } else if let a = value as? [Any] {
            self = .array(try a.map(WireValue.init))
        } else if value is NSNull {
            self = .null
        } else {
            throw SessionFailure.malformed
        }
    }
    var json: Any {
        switch self {
        case .string(let v): return v
        case .number(let v): return v
        case .flag(let v): return v
        case .object(let v): return v.mapValues(\.json)
        case .array(let v): return v.map(\.json)
        case .null: return NSNull()
        }
    }
    func object(_ keys: Set<String>) throws -> [String: WireValue] {
        guard case .object(let value) = self, Set(value.keys) == keys else { throw SessionFailure.malformed }
        return value
    }
    func text(_ maximum: Int = 64) throws -> String {
        guard case .string(let s) = self, !s.isEmpty, s.unicodeScalars.count <= maximum,
            !s.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 })
        else { throw SessionFailure.malformed }
        return s
    }
    func counter() throws -> UInt64 {
        guard case .number(let n) = self, n.isFinite, n >= 0, n <= Double(PlaybackScope.maximumGeneration),
            n.rounded() == n
        else { throw SessionFailure.malformed }
        return UInt64(n)
    }
    func flag() throws -> Bool {
        guard case .flag(let b) = self else { throw SessionFailure.malformed }
        return b
    }
    func position() throws -> Int64 {
        let n = try counter()
        guard n <= WatchSession.maximumPositionMs else { throw SessionFailure.malformed }
        return Int64(n)
    }
}

struct HelperFrame: Sendable {
    let kind: String
    let id: String
    let reply: Bool
    let afterUserAction: UInt64?
    let payload: [String: WireValue]
    let bytes: Data
}

enum HelperWire {
    static func decode(_ bytes: Data, scope: PlaybackScope) throws -> HelperFrame {
        // Foundation decoders accept duplicate keys. Reject them before decoding,
        // including equivalent escaped spellings and nested participant objects.
        var scanner = JSONMembers(bytes: Array(bytes))
        try scanner.check()
        let decoded = try JSONDecoder().decode(StrictJSON.self, from: bytes)
        guard case .object(let root) = decoded.value, let type = root["type"] else { throw SessionFailure.malformed }
        let kind = try type.text()
        let correction = ["player.setPaused", "player.setPosition", "player.setSpeed", "player.openFile"].contains(kind)
        let reply = ["bridge.ready", "bridge.result", "bridge.error", "bridge.stopped"].contains(kind)
        guard correction || reply || ["sync.connection", "sync.readiness", "sync.participants"].contains(kind) else {
            throw SessionFailure.malformed
        }
        let keys: Set<String> = ["v", "type", "clientRunId", "mediaGeneration", "payload", reply ? "replyTo" : "id"]
        guard Set(root.keys) == (correction ? keys.union(["afterUserAction"]) : keys), try root["v"]!.counter() == 1
        else { throw SessionFailure.malformed }
        try scope.check(clientRunID: root["clientRunId"]!.text(), mediaGeneration: root["mediaGeneration"]!.counter())
        let id = try root[reply ? "replyTo" : "id"]!.text()
        let prefix = reply || correction ? "cmd-" : "event-"
        guard id.hasPrefix(prefix), let number = UInt64(id.dropFirst(prefix.count)), number > 0,
            number <= PlaybackScope.maximumGeneration, id == prefix + String(number)
        else { throw SessionFailure.malformed }
        let payload = root["payload"]!
        let p: [String: WireValue]
        switch kind {
        case "player.setPaused":
            p = try payload.object(["paused"])
            _ = try p["paused"]!.flag()
        case "player.setPosition":
            p = try payload.object(["positionMs"])
            _ = try p["positionMs"]!.position()
        case "player.setSpeed":
            p = try payload.object(["rate"])
            guard case .number(let rate) = p["rate"], rate.isFinite, (0.25...4).contains(rate) else {
                throw SessionFailure.malformed
            }
        case "player.openFile":
            p = try payload.object(["mediaHandle"])
            _ = try PlaybackScope(clientRunID: p["mediaHandle"]!.text(), mediaGeneration: 0)
        case "bridge.ready":
            p = try payload.object(["syncplayRevision"])
            let revision = try p["syncplayRevision"]!.text(40)
            guard revision.count == 40, revision.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) })
            else { throw SessionFailure.malformed }
        case "bridge.result":
            p = try payload.object(["status"])
            guard try p["status"]!.text() == "applied" else { throw SessionFailure.malformed }
        case "bridge.stopped": p = try payload.object([])
        case "bridge.error":
            p = try payload.object(["code", "message", "retryable"])
            _ = try p["code"]!.text()
            _ = try p["message"]!.text(1024)
            _ = try p["retryable"]!.flag()
        case "sync.connection":
            p = try payload.object(["state"])
            guard ["connecting", "connected", "disconnected"].contains(try p["state"]!.text()) else {
                throw SessionFailure.malformed
            }
        case "sync.readiness":
            p = try payload.object(["ready"])
            _ = try p["ready"]!.flag()
        default:
            p = try payload.object(["participants"])
            guard case .array(let users) = p["participants"], users.count <= 64 else { throw SessionFailure.malformed }
            for user in users {
                let u = try user.object(["username", "ready"])
                _ = try u["username"]!.text()
                _ = try u["ready"]!.flag()
            }
        }
        return HelperFrame(
            kind: kind, id: id, reply: reply,
            afterUserAction: try correction ? root["afterUserAction"]!.counter() : nil, payload: p, bytes: bytes)
    }
    static func encode(
        _ scope: PlaybackScope, kind: String, payload: [String: WireValue], id: String? = nil,
        replyTo: String? = nil, user: UInt64? = nil
    ) throws -> Data {
        var value: [String: WireValue] = [
            "v": .number(1), "type": .string(kind), "clientRunId": .string(scope.clientRunID),
            "mediaGeneration": .number(Double(scope.mediaGeneration)), "payload": .object(payload),
        ]
        if let id { value["id"] = .string(id) }
        if let replyTo { value["replyTo"] = .string(replyTo) }
        if kind == "player.state" {
            value["origin"] = .string(user == nil ? "observation" : "user")
            if let user { value["actionSequence"] = .number(Double(user)) }
        }
        var bytes = try JSONSerialization.data(withJSONObject: value.mapValues(\.json), options: [.sortedKeys])
        bytes.append(10)
        return bytes
    }
}

/// Decodes JSON values without Foundation's boolean/number coercion.
private struct StrictJSON: Decodable {
    let value: WireValue
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() {
            value = .null
        } else if let b = try? c.decode(Bool.self) {
            value = .flag(b)
        } else if let n = try? c.decode(Double.self) {
            value = .number(n)
        } else if let s = try? c.decode(String.self) {
            value = .string(s)
        } else if let a = try? c.decode([StrictJSON].self) {
            value = .array(a.map(\.value))
        } else {
            value = .object(try c.decode([String: StrictJSON].self).mapValues(\.value))
        }
    }
}

private struct JSONMembers {
    let bytes: [UInt8]
    var index = 0
    mutating func whitespace() { while index < bytes.count && [9, 10, 13, 32].contains(bytes[index]) { index += 1 } }
    mutating func take(_ byte: UInt8) throws {
        whitespace()
        guard index < bytes.count, bytes[index] == byte else { throw SessionFailure.malformed }
        index += 1
    }
    mutating func string() throws -> String {
        whitespace()
        let start = index
        try take(34)
        while index < bytes.count {
            let byte = bytes[index]
            index += 1
            if byte == 34 { return try JSONDecoder().decode(String.self, from: Data(bytes[start..<index])) }
            if byte == 92 {
                guard index < bytes.count else { throw SessionFailure.malformed }
                index += 1
            }
        }
        throw SessionFailure.malformed
    }
    mutating func value(depth: Int) throws {
        whitespace()
        guard depth <= 8, index < bytes.count else { throw SessionFailure.malformed }
        switch bytes[index] {
        case 123:
            index += 1
            whitespace()
            var keys = Set<String>()
            if index < bytes.count && bytes[index] == 125 {
                index += 1
                return
            }
            while true {
                guard keys.insert(try string()).inserted else { throw SessionFailure.malformed }
                try take(58)
                try value(depth: depth + 1)
                whitespace()
                if index < bytes.count && bytes[index] == 125 {
                    index += 1
                    return
                }
                try take(44)
            }
        case 91:
            index += 1
            whitespace()
            if index < bytes.count && bytes[index] == 93 {
                index += 1
                return
            }
            while true {
                try value(depth: depth + 1)
                whitespace()
                if index < bytes.count && bytes[index] == 93 {
                    index += 1
                    return
                }
                try take(44)
            }
        case 34: _ = try string()
        default:
            let start = index
            while index < bytes.count && ![9, 10, 13, 32, 44, 93, 125].contains(bytes[index]) { index += 1 }
            guard index > start else { throw SessionFailure.malformed }
        }
    }
    mutating func check() throws {
        try value(depth: 1)
        whitespace()
        guard index == bytes.count else { throw SessionFailure.malformed }
    }
}
