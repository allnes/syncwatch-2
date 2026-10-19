using System.Windows;
using System.Windows.Controls;

namespace SyncWatch.Design;

public enum CallVisualState { Idle, Opening, WebSurfaceReady, UserActionRequired, Failed, Closed }
public enum CallPreviewState { CameraStarting, CameraActive, CameraDisabled, PermissionDenied, DeviceUnavailable }
public sealed record CallRequest(string Action, params double[] Values);

// Presentation observations only. Web-surface readiness does not establish call membership.
public sealed record CallPresentation
{
    public CallVisualState State { get; init; }
    public CallPreviewState Preview { get; init; } = CallPreviewState.CameraDisabled;
    public bool? Joined { get; init; }
    public bool? MicrophoneEnabled { get; init; }
    public bool? CameraEnabled { get; init; }
    public double? Volume { get; init; }
    public bool Pinned { get; init; }
    public bool Fullscreen { get; init; }
    public bool Minimized { get; init; }
    public IReadOnlySet<string> EnabledActions { get; init; } = new HashSet<string>();
    public bool ShowsRemoteSurface => State is CallVisualState.WebSurfaceReady or CallVisualState.UserActionRequired;
    public bool ShowsLocalPreview => State == CallVisualState.WebSurfaceReady && Joined == true && CameraEnabled == true && Preview == CallPreviewState.CameraActive;
    public double DisplayedVolume => Volume is double v && double.IsFinite(v) ? Math.Clamp(v, 0, 1) : 0;
    public string PreviewLabel(bool hasSurface) => Preview != CallPreviewState.CameraActive ? Key(Preview) : CameraEnabled == false ? "cameraDisabled" : ShowsLocalPreview && hasSurface ? "cameraActive" : "cameraStarting";
    internal static string Key<T>(T value) where T : Enum { var name = value.ToString(); return char.ToLowerInvariant(name[0]) + name[1..]; }
    public bool Allows(string action)
    {
        if (!EnabledActions.Contains(action) || !SyncWatchCall.Actions.Contains(action)) return false;
        if (action is "setCallVolume" or "setMicrophoneEnabled" or "setCameraEnabled" or "hangUp")
        {
            if (State != CallVisualState.WebSurfaceReady || Joined != true) return false;
            return action switch { "setCallVolume" => Volume is double v && double.IsFinite(v) && v is >= 0 and <= 1, "setMicrophoneEnabled" => MicrophoneEnabled is not null, "setCameraEnabled" => CameraEnabled is not null, _ => true };
        }
        return true;
    }
    public void Dispatch(CallRequest request, Action<CallRequest> handler)
    {
        if (!Allows(request.Action) || request.Values.Any(v => !double.IsFinite(v))) return;
        var v = request.Values;
        bool valid = SyncWatchCall.ActionKinds[request.Action] switch
        {
            "none" => v.Length == 0,
            "boolean" => v.Length == 1 && v[0] is 0 or 1,
            "volume" => v.Length == 1 && v[0] is >= 0 and <= 1,
            "delta" => v.Length == 2 && v.All(n => Math.Abs(n) <= SyncWatchCall.MaximumExtent),
            "size" => v.Length == 2 && v[0] >= SyncWatchTokens.LayoutCallMinimumWidth && v[1] >= SyncWatchTokens.LayoutCallMinimumHeight && v.All(n => n <= SyncWatchCall.MaximumExtent),
            _ => false,
        };
        if (valid) handler(request);
    }
    public static CallPresentation Gallery(CallGalleryCase item)
    {
        var state = Enum.Parse<CallVisualState>(item.State, true); var preview = Enum.Parse<CallPreviewState>(item.Preview, true);
        return new() { State = state, Preview = preview, Joined = state == CallVisualState.WebSurfaceReady, MicrophoneEnabled = true, CameraEnabled = preview != CallPreviewState.CameraDisabled, Volume = 0.7, EnabledActions = SyncWatchCall.Actions.ToHashSet() };
    }
    public CallPresentation ApplyingFixture(CallRequest request) => request.Action switch
    {
        "pin" => this with { Pinned = !Pinned },
        "fullscreen" => this with { Fullscreen = !Fullscreen },
        "minimize" => this with { Minimized = true },
        "restore" => this with { Minimized = false },
        "setCallVolume" => this with { Volume = request.Values[0] },
        "setMicrophoneEnabled" => this with { MicrophoneEnabled = request.Values[0] == 1 },
        "setCameraEnabled" => this with { CameraEnabled = request.Values[0] == 1, Preview = request.Values[0] == 1 ? CallPreviewState.CameraActive : CallPreviewState.CameraDisabled },
        "close" or "hangUp" => this with { State = CallVisualState.Closed, Joined = false, Preview = CallPreviewState.CameraDisabled },
        _ => this,
    };
}

// Owned content and input requests only. Composition belongs to the neutral Call document.
public sealed class CallWindowShell : UserControl
{
    public CallPresentation Presentation { get; private set; } = new();
    public string UiLanguage { get; private set; } = "en";
    public UIElement? RemoteSurface { get; set; }
    public UIElement? LocalPreview { get; set; }
    public event Action<CallRequest>? ActionRequested;
    private readonly DesignSurface surface = new("Call");
    public CallWindowShell()
    {
        Content = surface; surface.ConfigureHost(this);
        surface.EventRequested += e =>
        {
            var values = e.Value?.Split(',').Select(v => double.TryParse(v, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var number) ? number : double.NaN).ToArray() ?? [];
            Presentation.Dispatch(new(e.Action, values), request => ActionRequested?.Invoke(request));
        };
        Render(new());
    }
    public void Render(CallPresentation presentation, string language = "en")
    {
        if (RemoteSurface is not null && ReferenceEquals(RemoteSurface, LocalPreview)) throw new ArgumentException("Call surfaces must be distinct owned elements");
        Presentation = presentation; UiLanguage = language;
        if (presentation.ShowsRemoteSurface && RemoteSurface is not null) surface.Slots["remoteCallSurface"] = RemoteSurface; else surface.Slots.Remove("remoteCallSurface");
        if (presentation.ShowsLocalPreview && LocalPreview is not null) surface.Slots["localCameraPreview"] = LocalPreview; else surface.Slots.Remove("localCameraPreview");
        surface.Render(DesignBindings.Call(presentation, RemoteSurface is not null, LocalPreview is not null), language);
    }
}
