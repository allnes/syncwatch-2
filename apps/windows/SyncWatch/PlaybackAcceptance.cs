using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows;
using SyncWatch.Domain;

namespace SyncWatch;

// Runs only through the explicit development playback-report entry.
internal static class PlaybackAcceptance
{
    private static void Require(bool condition)
    {
        if (!condition) throw new InvalidOperationException("native surface acceptance");
    }
    private static async Task<PlaybackObservation> Wait(PlaybackWorkspace workspace, Func<PlaybackObservation, bool> predicate)
    {
        using CancellationTokenSource deadline = new(TimeSpan.FromSeconds(15));
        while (true)
        {
            PlaybackObservation value = await workspace.Player.ObserveAsync(workspace.Scope, deadline.Token);
            Require(value.Status != PlaybackStatus.Failed);
            if (predicate(value)) return value;
            await Task.Delay(40, deadline.Token);
        }
    }
    internal static async Task RunAsync(PlaybackWorkspace workspace, string report, bool detach)
    {
        Dictionary<string, object> result = new() { ["success"] = false, ["physicalOutputAccepted"] = false, ["presentedSeekPixelsAccepted"] = false };
        try
        {
            var player = workspace.Player; var scope = workspace.Scope;
            PlaybackObservation initial = await Wait(workspace, v => v.Status == PlaybackStatus.Ready && v.Paused && v.Seekable);
            Require(initial.DurationMs == 4000 && initial.PositionMs < 300);
            await player.SetPausedAsync(false, scope);
            await Wait(workspace, v => !v.Paused && v.PositionMs >= 500 && v.VideoOutputs > 0 && v.Width == 320 && v.Height == 180);
            nint drawable = workspace.Surface.NativeHandle;
            Require(IsWindow(drawable) && GetWindow(drawable, 5) != 0 && GetClientRect(drawable, out Rect rectangle) && rectangle.Right > 0 && rectangle.Bottom > 0);
            await player.SetPausedAsync(true, scope);
            PlaybackObservation paused = await Wait(workspace, v => v.Paused);
            await Task.Delay(300);
            Require(Math.Abs((await player.ObserveAsync(scope)).PositionMs - paused.PositionMs) <= 60);
            await player.SeekAsync(2500, scope);
            await Wait(workspace, v => v.Paused && v.PositionMs is >= 2300 and <= 2700);
            await player.SeekAsync(250, scope);
            await Wait(workspace, v => v.Paused && v.PositionMs < 650);
            Window window = Window.GetWindow(workspace);
            double width = window.Width, height = window.Height;
            window.Width = width * 1.1; window.Height = height * 1.1;
            await Task.Delay(200);
            Require(workspace.Surface.NativeHandle == drawable && (await player.ObserveAsync(scope)).VideoOutputs > 0);
            window.Width = width; window.Height = height;
            result["actualNativeSurface"] = true;
            result["actualPausedClock"] = true;
            result["resizeRetainedDrawable"] = true;
            if (detach)
            {
                await player.SetPausedAsync(false, scope);
                workspace.DetachSurface();
                await workspace.Surface.Destroyed.WaitAsync(TimeSpan.FromSeconds(15));
                Require(!IsWindow(drawable));
                result["unexpectedDetach"] = true;
                result["parkedUntilRelease"] = workspace.Surface.Parked;
            }
            await workspace.CloseAsync();
            try { await player.ObserveAsync(scope); throw new InvalidOperationException("still-open"); }
            catch (ObjectDisposedException) { }
            result["nativeReleasedBeforeView"] = true;
            result["success"] = true;
        }
        catch (Exception error)
        {
            result["failure"] = error.GetType().Name + ": " + error.Message;
            await workspace.CloseAsync();
        }
        Finish(report, result);
    }
    internal static void Finish(string report, Dictionary<string, object> result)
    {
        File.WriteAllText(report, JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
        Application.Current.MainWindow.Close();
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct Rect { internal int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWindow(nint window);
    [DllImport("user32.dll")]
    private static extern nint GetWindow(nint window, uint command);
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetClientRect(nint window, out Rect rectangle);
}
