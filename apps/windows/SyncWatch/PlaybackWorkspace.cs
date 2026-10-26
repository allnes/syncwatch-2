using System.IO;
using System.Windows;
using System.Windows.Controls;
using SyncWatch.Bridge;
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
        var media = MediaConfiguration.Read(arguments);
        return file is null ? null : new(Path.GetFullPath(file),
            media.Package, media.Bridge,
            Value("--playback-report"), arguments.Contains("--playback-detach-probe"));
    }
}

// Explicit local development entry. Normal room/watch capabilities remain gated.
internal sealed class PlaybackWorkspace : UserControl, IAsyncDisposable
{
    private readonly VLCPlayback player = new();
    private readonly PlaybackScope scope;
    private readonly PlayerChrome chrome = new();
    private readonly NativeVideoHost surface;
    private readonly LocalPlaybackLaunch launch;
    private string language;
    private readonly long initialPositionMs;
    private LibraryMediaSelection? selection;
    private readonly Action<PlaybackScope>? onLoaded;
    private readonly Action<PlaybackObservation>? onObservation;
    private readonly Action<string>? onNavigation;
    private readonly Action? onFailure;
    private readonly Action? onFullscreen;
    private HashSet<string> NavigationActions => onNavigation is null ? ["endWatching", "toggleFullscreen"] : ["endWatching", "toggleFullscreen", "showLibrary"];
    private readonly CancellationTokenSource cancellation = new();
    private PlayerPresentation presentation = new();
    private Task? polling, shutdown;
    private HelperSession? sharedSession;
    private readonly SharedMediaPreparation sharedMediaPreparation = new();
    internal HelperSessionState? SharedState { get; private set; }
    private bool closing;
    private bool attached;
    private bool fullscreen;
    private WindowState savedWindowState;
    private WindowStyle savedWindowStyle;
    internal VLCPlayback Player => player;
    internal PlaybackScope Scope => scope;
    internal NativeVideoHost Surface => surface;
    internal void RequestAction(string action, double? value = null) => Action(action, value);
    internal async Task<MediaDescriptor> PrepareSharedMediaAsync()
    {
        if (closing || selection is null) throw new InvalidOperationException("media-unavailable");
        var descriptor = await sharedMediaPreparation.PrepareAsync(selection, player, scope);
        if (closing) throw new OperationCanceledException();
        return descriptor;
    }
    // Transfer only after the room coordinator admits the selected local media.
    internal async Task ConnectSharedAsync(IHelperTransport transport, SyncplayEndpoint endpoint, SharedMedia media, string revision)
    {
        try
        {
            if (closing || !attached || sharedSession is not null) throw new InvalidOperationException("Shared playback unavailable");
            await sharedMediaPreparation.ValidateAsync(player, scope);
            if (closing || !attached || sharedSession is not null) throw new InvalidOperationException("Shared playback unavailable");
            var session = new HelperSession(transport, player, scope, endpoint, media, revision, state =>
            { SharedState = state; GateSharedActions(); chrome.Render(presentation, language); });
            sharedSession = session; SharedState = session.State; GateSharedActions(); chrome.Render(presentation, language);
            session.Start();
        }
        catch { await transport.DisposeAsync(); throw; }
    }
    private void GateSharedActions()
    {
        if (sharedSession is not null && SharedState is not { Connection: HelperConnection.Connected })
            presentation = presentation with { EnabledActions = presentation.EnabledActions.Except(["playPause", "seek", "skip"]).ToHashSet() };
    }
    internal void DetachSurface()
    {
        chrome.VideoSurface = null;
        chrome.Render(presentation, language);
    }

    public PlaybackWorkspace(LocalPlaybackLaunch launch, string language, PlaybackScope? scope = null, long positionMs = 0,
        LibraryMediaSelection? selection = null, Action<PlaybackScope>? onLoaded = null,
        Action<PlaybackObservation>? onObservation = null, Action<string>? onNavigation = null, Action? onFailure = null,
        Action? onFullscreen = null)
    {
        this.launch = launch; this.language = language;
        this.scope = scope ?? PlaybackScope.Create().ReplacingMedia(); initialPositionMs = positionMs;
        this.selection = selection; this.onLoaded = onLoaded; this.onObservation = onObservation;
        this.onNavigation = onNavigation; this.onFailure = onFailure;
        this.onFullscreen = onFullscreen;
        surface = new NativeVideoHost(CloseAsync);
        surface.SurfaceCreated += handle => { if (!attached && !cancellation.IsCancellationRequested) { attached = true; polling = PollAsync(handle); } };
        chrome.VideoSurface = surface;
        chrome.ActionRequested += Action;
        presentation = presentation with { Title = Path.GetFileName(launch.File), EnabledActions = NavigationActions };
        chrome.Render(presentation, language); Content = chrome;
    }
    public void SetLanguage(string value) { language = value; chrome.Render(presentation, language); }
    private async Task PollAsync(nint handle)
    {
        try
        {
            await player.OpenAsync(launch.Bridge, launch.Package, handle, cancellation.Token);
            await player.LoadAsync(launch.File, scope, cancellation.Token);
            onLoaded?.Invoke(scope);
            bool resumePending = initialPositionMs > 0;
            if (launch.Report is string report) _ = PlaybackAcceptance.RunAsync(this, report, launch.DetachProbe);
            while (!cancellation.IsCancellationRequested)
            {
                PlaybackObservation value = await player.ObserveAsync(scope, cancellation.Token);
                if (closing || cancellation.IsCancellationRequested) break;
                if (value.Status == PlaybackStatus.Failed) throw new PlaybackException("media");
                if (resumePending && value.Status == PlaybackStatus.Ready)
                {
                    resumePending = false;
                    if (value.Seekable)
                    {
                        try { await player.SeekAsync(Math.Min(initialPositionMs, value.DurationMs ?? initialPositionMs), scope, cancellation.Token); }
                        catch (PlaybackException) { /* The next actual observation remains authoritative. */ }
                        continue;
                    }
                }
                HashSet<string> enabled = NavigationActions; enabled.Add("playPause");
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
                GateSharedActions(); chrome.Render(presentation, language);
                onObservation?.Invoke(value);
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
                if (onFailure is not null) onFailure();
                else MessageBox.Show(Window.GetWindow(this), SyncWatchCopy.Text("playbackFailed", language), "SyncWatch", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }
    }
    private async void Action(string action, double? value)
    {
        if (closing || cancellation.IsCancellationRequested) return;
        if ((action is "endWatching" or "showLibrary") && onNavigation is not null) { onNavigation(action); return; }
        if (action == "endWatching")
        {
            Window window = Window.GetWindow(this);
            await CloseAsync(); window.Close(); return;
        }
        if (action == "toggleFullscreen")
        {
            if (onFullscreen is not null) { onFullscreen(); return; }
            Window window = Window.GetWindow(this);
            if (fullscreen) { window.WindowStyle = savedWindowStyle; window.WindowState = savedWindowState; }
            else
            {
                savedWindowState = window.WindowState; savedWindowStyle = window.WindowStyle;
                window.WindowStyle = WindowStyle.None; window.WindowState = WindowState.Maximized;
            }
            fullscreen = !fullscreen;
            return;
        }
        try
        {
            if (sharedSession is not null && action is "playPause" or "seek")
            {
                if (action == "playPause") sharedSession.TogglePause();
                else if (value is double position) sharedSession.Seek(checked((long)position));
                return;
            }
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
        closing = true;
        cancellation.Cancel();
        presentation = presentation with { EnabledActions = new HashSet<string>() };
        chrome.Render(presentation, language);
        await sharedMediaPreparation.CloseAsync();
        try { if (sharedSession is not null) await sharedSession.DisposeAsync(); }
        finally { sharedSession = null; await player.DisposeAsync(); }
        if (polling is not null) await polling;
        GC.KeepAlive(selection);
        selection = null;
    }
    public async ValueTask DisposeAsync() => await CloseAsync();
}
