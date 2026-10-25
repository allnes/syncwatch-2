import Darwin
import Foundation
import SyncWatchBridge
import SyncWatchDomain

func read(_ helper: HelperProcess) async throws -> String {
    let data = try await helper.read()
    let value = try JSONSerialization.jsonObject(with: data) as! [String: Any]
    return value["type"] as! String
}

@main
struct Probe {
    static func main() async throws {
        precondition(CommandLine.arguments.count == 3)
        let executable = URL(fileURLWithPath: CommandLine.arguments[1])
        let runtime = URL(fileURLWithPath: CommandLine.arguments[2])
        let commands = HelperCommands(wireScope: try PlaybackScope(clientRunID: "native-probe", mediaGeneration: 2))
        let helper = try await HelperProcess.launch(executable: executable, runtime: runtime)
        let hello = try commands.hello(1)
        try await helper.send(hello)
        let ready = try await read(helper)
        precondition(ready == "bridge.ready")
        try await helper.send(hello)
        let replay = try await read(helper)
        precondition(replay == "bridge.ready")
        try await helper.send(
            commands.loaded(2, handle: "media-1", name: "Movie.mkv", durationMs: 60_000, fileSizeBytes: 1234))
        let loaded = try await read(helper)
        precondition(loaded == "bridge.result")
        try await helper.send(commands.shutdown(3))
        let stopped = try await read(helper)
        precondition(stopped == "bridge.stopped")
        await helper.close()

        let cancelled = try await HelperProcess.launch(executable: executable, runtime: runtime)
        let pending = Task { try await cancelled.read() }
        try await Task.sleep(nanoseconds: 100_000_000)
        pending.cancel()
        do {
            _ = try await pending.value
            preconditionFailure("Cancellation was ignored")
        } catch {}
        await cancelled.close()

        let crashed = try await HelperProcess.launch(executable: executable, runtime: runtime)
        _ = Darwin.kill(crashed.processID, SIGKILL)
        do {
            _ = try await crashed.read()
            preconditionFailure("Crash was ignored")
        } catch {}
        await crashed.close()
        print("SYNCWATCH_NATIVE_BRIDGE_OK handshake replay media shutdown cancellation crash")
    }
}
