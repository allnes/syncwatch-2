using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Media;

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

// Host-owned slots and input requests only. Hiding a slot is not provider/audio teardown.
public sealed class CallWindowShell : UserControl
{
    public CallPresentation Presentation { get; private set; } = new();
    public string UiLanguage { get; private set; } = "en";
    public UIElement? RemoteSurface { get; set; }
    public UIElement? LocalPreview { get; set; }
    public event Action<CallRequest>? ActionRequested;
    private readonly Grid root = new();
    private readonly Border chrome;
    public CallWindowShell()
    {
        MinWidth = SyncWatchTokens.LayoutCallMinimumWidth; MinHeight = SyncWatchTokens.LayoutCallMinimumHeight;
        FontSize = SyncWatchTokens.TypePlayerLabelSize;
        chrome = new Border { Child = root, BorderThickness = new Thickness(SyncWatchTokens.ControlBorderWidth) };
        chrome.SetResourceReference(Border.BackgroundProperty, "theme.backgroundDeep.brush"); chrome.SetResourceReference(Border.BorderBrushProperty, "theme.border.brush");
        Content = chrome; SizeChanged += (_, _) => ClipShell(); Render(new());
    }
    private void ClipShell()
    {
        double radius = Presentation.Fullscreen ? 0 : SyncWatchTokens.LayoutCallRadius;
        chrome.CornerRadius = new CornerRadius(radius); chrome.Clip = new RectangleGeometry(new Rect(0, 0, Math.Max(0, ActualWidth), Math.Max(0, ActualHeight)), radius, radius);
    }
    private string T(string key) => SyncWatchCopy.Text(key, UiLanguage);
    private void Emit(string action, params double[] values) => Presentation.Dispatch(new(action, values), request => ActionRequested?.Invoke(request));
    private static void Detach(UIElement? surface)
    {
        if (surface is null) return;
        var parent = VisualTreeHelper.GetParent(surface);
        if (parent is Panel panel) panel.Children.Remove(surface);
        else if (parent is not null) throw new InvalidOperationException("Supply a detached, host-owned call surface");
    }
    public void Render(CallPresentation presentation, string language = "en")
    {
        if (RemoteSurface is not null && ReferenceEquals(RemoteSurface, LocalPreview)) throw new ArgumentException("Call surfaces must be distinct owned elements");
        Detach(RemoteSurface); Detach(LocalPreview);
        Presentation = presentation; UiLanguage = language; Language = System.Windows.Markup.XmlLanguage.GetLanguage(language);
        root.Children.Clear(); root.RowDefinitions.Clear();
        root.RowDefinitions.Add(new() { Height = new GridLength(SyncWatchTokens.LayoutCallHeaderHeight) }); root.RowDefinitions.Add(new()); root.RowDefinitions.Add(new() { Height = new GridLength(SyncWatchTokens.LayoutCallFooterHeight) });
        var header = new Grid { Margin = new Thickness(SyncWatchTokens.LayoutCallInset, 0, SyncWatchTokens.LayoutCallInset, 0) };
        header.ColumnDefinitions.Add(new()); header.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        var title = Text(T("callWindow")); title.TextTrimming = TextTrimming.CharacterEllipsis; header.Children.Add(title);
        var mover = Gesture("moveCall", "move", (x, y) => Emit("move", x, y)); header.Children.Add(mover);
        var controls = Row();
        controls.Children.Add(Button("pin", "pin", presentation.Pinned ? "unpinCall" : "pinCall", small: true, active: presentation.Pinned));
        controls.Children.Add(Button(presentation.Minimized ? "restore" : "minimize", presentation.Minimized ? "restore" : "minimize", presentation.Minimized ? "restoreCall" : "minimizeCall", small: true));
        controls.Children.Add(Button("fullscreen", presentation.Fullscreen ? "restore" : "fullscreen", presentation.Fullscreen ? "exitFullscreenCall" : "fullscreenCall", small: true)); controls.Children.Add(Button("close", "close", "closeCall", small: true));
        Grid.SetColumn(controls, 1); header.Children.Add(controls); root.Children.Add(header);
        var body = new Grid { ClipToBounds = true }; body.SetResourceReference(BackgroundProperty, "color.shared.videoSurface.brush"); AutomationProperties.SetName(body, T("callSurface"));
        if (presentation.ShowsRemoteSurface && RemoteSurface is not null) body.Children.Add(RemoteSurface);
        else { var state = Text(T("callState" + presentation.State)); state.Foreground = Brushes.White; state.TextAlignment = TextAlignment.Center; state.TextWrapping = TextWrapping.Wrap; state.Margin = new Thickness(SyncWatchTokens.LayoutCallInset); body.Children.Add(state); }
        var preview = new Grid { Width = SyncWatchTokens.LayoutCallPreviewWidth, Height = SyncWatchTokens.LayoutCallPreviewHeight, ClipToBounds = true }; preview.SetResourceReference(BackgroundProperty, "theme.surfaceRaised.brush");
        if (presentation.ShowsLocalPreview && LocalPreview is not null) preview.Children.Add(LocalPreview);
        else { var label = Text(T(presentation.PreviewLabel(LocalPreview is not null)), true); label.FontSize = SyncWatchTokens.TypeCaptionSize; label.TextAlignment = TextAlignment.Center; label.TextWrapping = TextWrapping.Wrap; label.Margin = new Thickness(2); preview.Children.Add(label); }
        AutomationProperties.SetAutomationId(preview, "call.localPreview"); AutomationProperties.SetName(preview, T(presentation.PreviewLabel(LocalPreview is not null)));
        var previewFrame = new Border { Child = preview, BorderThickness = new Thickness(SyncWatchTokens.ControlBorderWidth), CornerRadius = SyncWatchTokens.ControlFieldRadiusCornerRadius, Margin = SyncWatchTokens.LayoutCallInsetThickness, HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Top }; previewFrame.SetResourceReference(Border.BorderBrushProperty, "theme.border.brush"); body.Children.Add(previewFrame);
        Grid.SetRow(body, 1); root.Children.Add(body);
        var footer = Row(); footer.HorizontalAlignment = HorizontalAlignment.Center;
        footer.Children.Add(Button("setMicrophoneEnabled", "microphone", presentation.MicrophoneEnabled == true ? "microphoneOff" : "microphoneOn", [presentation.MicrophoneEnabled == true ? 0 : 1], active: presentation.MicrophoneEnabled == true, slash: presentation.MicrophoneEnabled == false));
        footer.Children.Add(Button("setCameraEnabled", "camera", presentation.CameraEnabled == true ? "cameraOff" : "cameraOn", [presentation.CameraEnabled == true ? 0 : 1], active: presentation.CameraEnabled == true, slash: presentation.CameraEnabled == false)); footer.Children.Add(Button("hangUp", "end", "hangUp"));
        footer.Children.Add(Icon(presentation.DisplayedVolume > 0 ? "volume" : "muted", false));
        var volume = new Slider { Minimum = 0, Maximum = 1, Value = presentation.DisplayedVolume, Width = SyncWatchTokens.LayoutCallVolumeWidth, SmallChange = 0.05, LargeChange = 0.1, IsEnabled = presentation.Allows("setCallVolume"), Margin = new Thickness(SyncWatchTokens.LayoutCallGap / 2, 0, SyncWatchTokens.LayoutCallGap / 2, 0) };
        volume.SetResourceReference(StyleProperty, "SyncWatch.PlayerSlider"); AutomationProperties.SetName(volume, T("callVolume")); AutomationProperties.SetAutomationId(volume, "call.setCallVolume");
        // Observation-driven initialization precedes event subscription, so it cannot echo input.
        volume.ValueChanged += (_, e) => Emit("setCallVolume", e.NewValue); footer.Children.Add(volume); Grid.SetRow(footer, 2); root.Children.Add(footer);
        var resize = Gesture("resizeCall", "resize", (x, y) => Emit("resize", Math.Clamp(ActualWidth + x, MinWidth, SyncWatchCall.MaximumExtent), Math.Clamp(ActualHeight + y, MinHeight, SyncWatchCall.MaximumExtent)));
        resize.Width = SyncWatchTokens.LayoutCallResizeSize; resize.Height = SyncWatchTokens.LayoutCallResizeSize; resize.HorizontalAlignment = HorizontalAlignment.Right; resize.VerticalAlignment = VerticalAlignment.Bottom; resize.Margin = new Thickness(2);
        var grip = Icon("resize", false); grip.Width = resize.Width; grip.Height = resize.Height; grip.HorizontalAlignment = HorizontalAlignment.Right; grip.VerticalAlignment = VerticalAlignment.Bottom; grip.IsHitTestVisible = false; grip.Margin = new Thickness(2); Grid.SetRow(grip, 2); root.Children.Add(grip); Grid.SetRow(resize, 2); root.Children.Add(resize); ClipShell();
    }
    private Thumb Gesture(string label, string action, Action<double, double> move)
    {
        var factory = new FrameworkElementFactory(typeof(Border)); factory.SetValue(Border.BackgroundProperty, Brushes.Transparent);
        var thumb = new Thumb { Template = new ControlTemplate(typeof(Thumb)) { VisualTree = factory }, Focusable = true, IsEnabled = Presentation.Allows(action) };
        AutomationProperties.SetName(thumb, T(label)); AutomationProperties.SetAutomationId(thumb, "call." + action);
        thumb.DragDelta += (_, e) => move(e.HorizontalChange, e.VerticalChange);
        thumb.KeyDown += (_, e) => { if (e.Key is Key.Left or Key.Right or Key.Up or Key.Down) { move(e.Key == Key.Left ? -10 : e.Key == Key.Right ? 10 : 0, e.Key == Key.Up ? -10 : e.Key == Key.Down ? 10 : 0); e.Handled = true; } }; return thumb;
    }
    private static StackPanel Row() => new() { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
    private TextBlock Text(string value, bool muted = false) { var text = new TextBlock { Text = value, VerticalAlignment = VerticalAlignment.Center }; text.SetResourceReference(TextBlock.ForegroundProperty, muted ? "theme.textSecondary.brush" : "theme.text.brush"); return text; }
    private FrameworkElement Icon(string name, bool active, bool slash = false)
    {
        var geometry = new GeometryGroup { FillRule = FillRule.Nonzero };
        foreach (var polygon in SyncWatchCall.Icons[name].Concat(slash ? SyncWatchCall.Icons["slash"] : []))
        {
            var figure = new PathFigure { StartPoint = new Point(polygon[0], polygon[1]), IsClosed = true, IsFilled = true };
            for (int i = 2; i < polygon.Length; i += 2) figure.Segments.Add(new LineSegment(new Point(polygon[i], polygon[i + 1]), true)); geometry.Children.Add(new PathGeometry([figure]));
        }
        var icon = new System.Windows.Shapes.Path { Data = geometry, Width = SyncWatchTokens.LayoutCallIconSize, Height = SyncWatchTokens.LayoutCallIconSize, Stretch = Stretch.Uniform, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0) };
        icon.SetResourceReference(System.Windows.Shapes.Shape.FillProperty, active ? "color.dark.text.brush" : "theme.text.brush"); return icon;
    }
    private Button Button(string action, string icon, string label, double[]? values = null, bool small = false, bool active = false, bool slash = false)
    {
        var button = new Button { Content = Icon(icon, active || action == "hangUp", slash), IsEnabled = Presentation.Allows(action), ToolTip = T(label), Width = small ? SyncWatchTokens.LayoutCallWindowButtonSize : SyncWatchTokens.LayoutCallButtonSize, Height = small ? SyncWatchTokens.LayoutCallWindowButtonSize : SyncWatchTokens.LayoutCallButtonSize, Margin = new Thickness((small ? SyncWatchTokens.LayoutCallGap / 2 : SyncWatchTokens.LayoutCallGap) / 2, 0, (small ? SyncWatchTokens.LayoutCallGap / 2 : SyncWatchTokens.LayoutCallGap) / 2, 0) };
        button.SetResourceReference(StyleProperty, "SyncWatch.PlayerButton"); if (active || action == "hangUp") button.SetResourceReference(BackgroundProperty, action == "hangUp" ? "color.shared.callHangup.brush" : "theme.accent.brush");
        AutomationProperties.SetName(button, T(label)); AutomationProperties.SetAutomationId(button, "call." + action); button.Click += (_, _) => Emit(action, values ?? []); return button;
    }
}

public sealed class CallGallery : UserControl
{
    private CallPresentation presentation = CallPresentation.Gallery(SyncWatchCall.GalleryCases[2]);
    private readonly CallWindowShell shell = new() { Width = SyncWatchTokens.LayoutCallInitialWidth, Height = SyncWatchTokens.LayoutCallInitialHeight };
    private readonly TextBlock last = new();
    private string language = "en";
    public CallGallery()
    {
        var root = new StackPanel { VerticalAlignment = VerticalAlignment.Center, HorizontalAlignment = HorizontalAlignment.Center };
        var bar = new StackPanel { Orientation = Orientation.Horizontal };
        var states = new ComboBox { ItemsSource = SyncWatchCall.GalleryCases.Select(c => c.Id), SelectedItem = "ready", Width = 150 }; states.SelectionChanged += (_, _) => { presentation = CallPresentation.Gallery(SyncWatchCall.GalleryCases.Single(c => c.Id == (string)states.SelectedItem)); Render(); }; bar.Children.Add(states);
        var locales = new ComboBox { ItemsSource = new[] { "en", "ru" }, SelectedIndex = 0, Width = 80 }; locales.SelectionChanged += (_, _) => { language = (string)locales.SelectedItem; Render(); }; bar.Children.Add(locales);
        var themes = new ComboBox { ItemsSource = new[] { "dark", "light" }, SelectedIndex = 0, Width = 100 }; themes.SelectionChanged += (_, _) => { var resources = Application.Current.Resources; var dictionary = resources.MergedDictionaries.First(d => d.Contains("theme.dark")); resources.MergedDictionaries.Add((ResourceDictionary)dictionary["theme." + themes.SelectedItem]); }; bar.Children.Add(themes); root.Children.Add(bar);
        root.Children.Add(shell); root.Children.Add(new TextBlock { Text = SyncWatchCopy.Text("callFixture"), TextWrapping = TextWrapping.Wrap, Width = 360 }); root.Children.Add(last); Content = root;
        shell.ActionRequested += request => { last.Text = request.Action; presentation = presentation.ApplyingFixture(request); Render(); }; Render();
    }
    private void Render()
    {
        shell.RemoteSurface = new TextBlock { Text = SyncWatchCopy.Text("remoteFixture", language), Foreground = Brushes.White, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center };
        var preview = new Grid(); preview.SetResourceReference(BackgroundProperty, "theme.accent.brush"); preview.Children.Add(new TextBlock { Text = SyncWatchCopy.Text("localFixture", language), Foreground = Brushes.White, FontSize = SyncWatchTokens.TypeCaptionSize, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center }); shell.LocalPreview = preview; shell.Render(presentation, language);
    }
}
