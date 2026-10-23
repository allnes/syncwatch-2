using System.IO;
using System.Windows;
using System.Windows.Controls;
using SyncWatch.Design;
using SyncWatch.Domain;
using SyncWatch.Playback;

namespace SyncWatch;

internal sealed record LocalPlaybackLaunch(string File, string Package, string Bridge, string? Report, bool DetachProbe)
{
    public static LocalPlaybackLaunch? Read(string[] arguments)
    {
        string? Value(string flag) { int i = Array.IndexOf(arguments, flag); return i >= 0 && i + 1 < arguments.Length ? arguments[i + 1] : null; }
        string? file = Value("--local-playback");
        return file is null ? null : new(Path.GetFullPath(file),
            Value("--media-package") ?? Path.Combine(AppContext.BaseDirectory, "Media"),
            Value("--playback-bridge") ?? Path.Combine(AppContext.BaseDirectory, "syncwatch_playback.dll"),
            Value("--playback-report"), arguments.Contains("--playback-detach-probe"));
    }
}

// Explicit local development entry. Normal room/watch capabilities remain gated.
internal sealed class PlaybackWorkspace : UserControl, IAsyncDisposable
{
    private readonly VLCPlayback player = new();
    private readonly PlaybackScope scope = PlaybackScope.Create().ReplacingMedia();
    private readonly PlayerChrome chrome = new();
    private readonly NativeVideoHost surface;
    private readonly LocalPlaybackLaunch launch;
    private readonly string language;
    private readonly CancellationTokenSource cancellation = new();
    private PlayerPresentation presentation = new();
    private Task? polling, shutdown;
    private bool attached;
    internal VLCPlayback Player => player;
    internal PlaybackScope Scope => scope;
    internal NativeVideoHost Surface => surface;
    internal void DetachSurface()
    {
        chrome.VideoSurface = null;
        chrome.Render(presentation, language);
    }

    public PlaybackWorkspace(LocalPlaybackLaunch launch, string language)
    {
        this.launch = launch; this.language = language;
        surface = new NativeVideoHost(CloseAsync);
        surface.SurfaceCreated += handle => { if (!attached) { attached = true; polling = PollAsync(handle); } };
        chrome.VideoSurface = surface;
        chrome.ActionRequested += Action;
        presentation = presentation with { Title = Path.GetFileName(launch.File), EnabledActions = new HashSet<string> { "endWatching", "toggleFullscreen" } };
        chrome.Render(presentation, language); Content = chrome;
    }
    private async Task PollAsync(nint handle)
    {
        try
        {
            await player.OpenAsync(launch.Bridge, launch.Package, handle, cancellation.Token);
            await player.LoadAsync(launch.File, scope, cancellation.Token);
            if (launch.Report is string report) _ = PlaybackAcceptance.RunAsync(this, report, launch.DetachProbe);
            while (!cancellation.IsCancellationRequested)
            {
                PlaybackObservation value = await player.ObserveAsync(scope, cancellation.Token);
                if (cancellation.IsCancellationRequested) break;
                if (value.Status == PlaybackStatus.Failed) throw new PlaybackException("media");
                HashSet<string> enabled = ["endWatching", "toggleFullscreen", "playPause"];
                if (value.Seekable) enabled.UnionWith(["seek", "skip"]);
                if (value.Volume is not null) enabled.UnionWith(["setMovieVolume", "muteMovie"]);
                presentation = presentation with
                {
                    State = value.Ended ? PlayerVisualState.Ended : value.Buffering ? PlayerVisualState.Buffering : value.Status != PlaybackStatus.Ready ? PlayerVisualState.Loading : value.Paused ? PlayerVisualState.Paused : PlayerVisualState.Playing,
                    PositionMs = value.PositionMs,
                    DurationMs = value.DurationMs ?? 0,
                    Volume = value.Volume ?? presentation.Volume,
                    Muted = value.Muted,
                    EnabledActions = enabled,
                };
                chrome.Render(presentation, language);
                await Task.Delay(100, cancellation.Token);
            }
        }
        catch (OperationCanceledException) { }
        catch (ObjectDisposedException) when (cancellation.IsCancellationRequested) { }
        catch (Exception)
        {
            if (!cancellation.IsCancellationRequested)
            {
                presentation = presentation with { EnabledActions = new HashSet<string> { "endWatching" } };
                chrome.Render(presentation, language);
                if (launch.Report is string report)
                {
                    await player.DisposeAsync();
                    PlaybackAcceptance.Finish(report, new() { ["success"] = false, ["failure"] = "startup", ["physicalOutputAccepted"] = false });
                    return;
                }
                MessageBox.Show(Window.GetWindow(this), SyncWatchCopy.Text("playbackFailed", language), "SyncWatch", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }
    }
    private async void Action(string action, double? value)
    {
        if (cancellation.IsCancellationRequested) return;
        if (action == "endWatching")
        {
            Window window = Window.GetWindow(this);
            await CloseAsync(); window.Close(); return;
        }
        if (action == "toggleFullscreen")
        {
            Window window = Window.GetWindow(this);
            if (window.WindowState == WindowState.Maximized) { window.WindowState = WindowState.Normal; window.WindowStyle = WindowStyle.SingleBorderWindow; }
            else { window.WindowStyle = WindowStyle.None; window.WindowState = WindowState.Maximized; }
            return;
        }
        try
        {
            switch (action)
            {
                case "playPause": await player.SetPausedAsync(presentation.Playing, scope, cancellation.Token); break;
                case "seek" when value is double seek: await player.SeekAsync(checked((long)seek), scope, cancellation.Token); break;
                case "setMovieVolume" when value is double volume: await player.SetVolumeAsync(volume, presentation.Muted, scope, cancellation.Token); break;
                case "muteMovie": await player.SetVolumeAsync(presentation.Volume, !presentation.Muted, scope, cancellation.Token); break;
            }
        }
        catch (Exception) { /* A rejected request never changes the observation. */ }
    }
    public Task CloseAsync() => shutdown ??= CloseCoreAsync();
    private async Task CloseCoreAsync()
    {
        cancellation.Cancel();
        presentation = presentation with { EnabledActions = new HashSet<string>() };
        chrome.Render(presentation, language);
        await player.DisposeAsync();
        if (polling is not null) await polling;
    }
    public async ValueTask DisposeAsync() => await CloseAsync();
}
