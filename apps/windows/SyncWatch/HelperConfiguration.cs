using System.IO;
using SyncWatch.Bridge;

namespace SyncWatch;

// Local installation configuration. Room metadata never supplies executable or runtime paths.
internal sealed record HelperConfiguration(string Package)
{
    internal static HelperConfiguration Read(string[] arguments, string? directory = null)
    {
        int index = Array.IndexOf(arguments, "--helper-package");
        string package = index >= 0 && index + 1 < arguments.Length ? arguments[index + 1] : Path.Combine(directory ?? AppContext.BaseDirectory, "Syncplay");
        return new(Path.GetFullPath(package));
    }
    internal Task<HelperRuntime> VerifyAsync(CancellationToken cancellation = default) => Task.Run(() =>
    {
        cancellation.ThrowIfCancellationRequested();
        var runtime = HelperRuntime.Verify(Package, cancellation);
        cancellation.ThrowIfCancellationRequested();
        return runtime;
    }, cancellation);
}
