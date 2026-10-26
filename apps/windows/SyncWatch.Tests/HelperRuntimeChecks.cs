using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using SyncWatch.Bridge;

internal static class HelperRuntimeChecks
{
    internal static void Run()
    {
        string temporary = Path.Combine(Path.GetTempPath(), "sw-helper-integrity-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temporary);
        try
        {
            foreach (string name in new[] { "valid", "wrongTarget", "wrongPin", "wrongRevisionFile", "changedFile", "extraFile", "missingFile", "pathEscape", "entryLink" })
            {
                string root = Path.Combine(temporary, name), executable = Path.Combine(root, "bin", "syncwatch-helper.exe");
                Directory.CreateDirectory(Path.Combine(root, "bin")); Directory.CreateDirectory(Path.Combine(root, "app"));
                File.WriteAllText(executable, "owned test stub; never executed");
                File.WriteAllText(Path.Combine(root, "app", "syncplay-revision.txt"), (name == "wrongRevisionFile" ? new string('0', 40) : HelperRuntime.ExpectedRevision) + "\n");
                var files = new Dictionary<string, string>();
                foreach (string relative in new[] { "bin/syncwatch-helper.exe", "app/syncplay-revision.txt" })
                    files[relative] = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(Path.Combine(root, relative))));
                if (name == "pathEscape") files["../outside"] = new string('a', 64);
                File.WriteAllBytes(Path.Combine(root, "helper-report.json"), JsonSerializer.SerializeToUtf8Bytes(new
                {
                    schemaVersion = 1, target = name == "wrongTarget" ? "linux-x64" : "windows-x64",
                    syncplayRevision = name == "wrongPin" ? new string('0', 40) : HelperRuntime.ExpectedRevision,
                    developmentHelperOnly = true, authenticatedInstallation = false, files
                }));
                if (name == "changedFile") File.WriteAllText(executable, "changed");
                if (name == "extraFile") File.WriteAllText(Path.Combine(root, "extra"), "");
                if (name == "missingFile") File.Delete(executable);
                // Windows directory junctions need no symbolic-link privilege; their target is owned.
                if (name == "entryLink")
                {
                    var start = new ProcessStartInfo("cmd.exe") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true };
                    foreach (string argument in new[] { "/c", "mklink", "/J", Path.Combine(root, "link"), Path.Combine(root, "bin") }) start.ArgumentList.Add(argument);
                    using var link = Process.Start(start)!;
                    if (!link.WaitForExit(5000)) { link.Kill(true); link.WaitForExit(); throw new Exception("Junction fixture deadline"); }
                    if (link.ExitCode != 0) throw new Exception("Junction fixture unavailable");
                }
                bool accepted = false;
                try { _ = HelperRuntime.Verify(root); _ = HelperRuntime.Verify(root); accepted = true; }
                catch (Exception) { }
                if (name == "entryLink") Directory.Delete(Path.Combine(root, "link"));
                if (accepted != (name == "valid")) throw new Exception("helper integrity: " + name);
            }
            using var stop = new CancellationTokenSource(); stop.Cancel();
            bool cancelled = false;
            try { _ = HelperRuntime.Verify(Path.Combine(temporary, "valid"), stop.Token); }
            catch (OperationCanceledException) { cancelled = true; }
            if (!cancelled) throw new Exception("Cancelled helper verification succeeded");
            if (Environment.GetEnvironmentVariable("SYNCWATCH_VERIFY_HELPER_PACKAGE") is string real) _ = HelperRuntime.Verify(real);
            if (Environment.GetEnvironmentVariable("SYNCWATCH_REJECT_HELPER_PACKAGE") is string derivative)
            {
                bool rejected = false;
                try { _ = HelperRuntime.Verify(derivative); } catch (Exception) { rejected = true; }
                if (!rejected) throw new Exception("Instrumented test package was admitted");
            }
            Console.WriteLine("SYNCWATCH_HELPER_RUNTIME_OK integrity/pins/membership/cancellation");
        }
        finally { Directory.Delete(temporary, true); }
    }
}
