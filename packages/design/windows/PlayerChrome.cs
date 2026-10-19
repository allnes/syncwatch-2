using System.Globalization;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Shapes;

namespace SyncWatch.Design;

public enum PlayerVisualState { Loading, Paused, Playing, Buffering, Fullscreen, ConnectionInterrupted, Ended }

// Immutable observations/capabilities. Dispatching a request never changes the observed position/state.
public sealed record PlayerPresentation
{
    public PlayerVisualState State { get; init; }
    public string Title { get; init; } = "";
    public long PositionMs { get; init; }
    public long DurationMs { get; init; }
    public double Volume { get; init; } = 1;
    public bool Muted { get; init; }
    public int SkipSeconds { get; init; } = 10;
    public bool HasPrevious { get; init; }
    public bool HasNext { get; init; }
    public IReadOnlySet<string> EnabledActions { get; init; } = new HashSet<string>();
    public bool IsValid => DurationMs is >= 0 and <= SyncWatchPlayer.MaximumPositionMs && PositionMs >= 0 && PositionMs <= DurationMs && double.IsFinite(Volume) && Volume is >= 0 and <= 1 && SkipSeconds is >= 1 and <= 600;
    public bool Playing => State is PlayerVisualState.Playing or PlayerVisualState.Fullscreen;
    public double DisplayedDuration => Math.Clamp(DurationMs, 0, SyncWatchPlayer.MaximumPositionMs);
    public double DisplayedPosition => Math.Clamp(PositionMs, 0, DisplayedDuration);
    public bool Allows(string action)
    {
        if (!EnabledActions.Contains(action) || !SyncWatchPlayer.Actions.Contains(action)) return false;
        return action switch
        {
            "playPause" or "seek" or "skip" or "previousFile" or "nextFile" => IsValid && (State is PlayerVisualState.Paused or PlayerVisualState.Playing or PlayerVisualState.Fullscreen) && (action switch
            {
                "seek" or "skip" => DurationMs > 0,
                "previousFile" => HasPrevious,
                "nextFile" => HasNext,
                _ => true,
            }),
            "setMovieVolume" or "muteMovie" => IsValid,
            _ => true,
        };
    }
    public void Dispatch(string action, double? value, Action<string, double?> handler)
    {
        if (!Allows(action)) return;
        switch (action)
        {
            case "seek": if (value is not double seek || !double.IsFinite(seek) || Math.Round(seek) != seek || seek < 0 || seek > DurationMs) return; break;
            case "skip":
                if (value is not (-1 or 1) || !Allows("seek")) return;
                double target = Math.Clamp(PositionMs + value.Value * SkipSeconds * 1000, 0, DurationMs);
                if (target != PositionMs) handler("seek", target);
                return;
            case "setMovieVolume": if (value is not double volume || !double.IsFinite(volume) || volume is < 0 or > 1) return; break;
            default: if (value is not null) return; break;
        }
        handler(action, value);
    }
    public static string Time(double milliseconds)
    {
        long seconds = (long)Math.Clamp(double.IsFinite(milliseconds) ? milliseconds : 0, 0, SyncWatchPlayer.MaximumPositionMs) / 1000;
        return seconds >= 3600 ? string.Create(CultureInfo.InvariantCulture, $"{seconds / 3600}:{seconds / 60 % 60:00}:{seconds % 60:00}") : string.Create(CultureInfo.InvariantCulture, $"{seconds / 60:00}:{seconds % 60:00}");
    }
    public static PlayerPresentation Gallery(PlayerVisualState state) => new()
    {
        State = state,
        Title = SyncWatchCopy.GalleryMovies[1],
        DurationMs = state == PlayerVisualState.Loading ? 0 : 5_400_000,
        PositionMs = state == PlayerVisualState.Loading ? 0 : state == PlayerVisualState.Ended ? 5_400_000 : 754_000,
        Volume = 0.7,
        HasPrevious = true,
        HasNext = true,
        EnabledActions = new HashSet<string>(SyncWatchPlayer.Actions),
    };
}

public sealed class PlayerChrome : UserControl
{
    public PlayerPresentation Presentation { get; private set; } = new();
    public string UiLanguage { get; private set; } = "en";
    public event Action<string, double?>? ActionRequested;
    public UIElement? VideoSurface { get; set; }
    private readonly Grid root = new();
    public PlayerChrome()
    {
        Content = root;
        MinWidth = SyncWatchTokens.LayoutMinimumWidth;
        MinHeight = SyncWatchTokens.LayoutMinimumHeight;
        FontSize = SyncWatchTokens.TypePlayerLabelSize;
        SetResourceReference(ForegroundProperty, "theme.text.brush");
        Render(new());
    }
    private string T(string key) => SyncWatchCopy.Text(key, UiLanguage);
    private void Emit(string action, double? value = null) => Presentation.Dispatch(action, value, (a, v) => ActionRequested?.Invoke(a, v));
    public void Render(PlayerPresentation presentation, string language = "en")
    {
        Presentation = presentation; UiLanguage = language;
        Language = System.Windows.Markup.XmlLanguage.GetLanguage(language);
        // Detach supplied video content before rebuilding, preserving its single WPF parent.
        if (VideoSurface is not null && VisualTreeHelper.GetParent(VideoSurface) is Panel oldParent) oldParent.Children.Remove(VideoSurface);
        root.Children.Clear(); root.RowDefinitions.Clear();
        root.RowDefinitions.Add(new() { Height = new GridLength(SyncWatchTokens.LayoutPlayerToolbarHeight) });
        root.RowDefinitions.Add(new());
        root.RowDefinitions.Add(new() { Height = new GridLength(SyncWatchTokens.LayoutPlayerFooterHeight) });
        var top = new Grid { Margin = new Thickness(SyncWatchTokens.LayoutPanelPadding, 0, SyncWatchTokens.LayoutPanelPadding, 0) };
        top.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); top.ColumnDefinitions.Add(new()); top.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        top.Children.Add(Button("showLibrary", "library"));
        var title = Text(Presentation.Title); title.TextTrimming = TextTrimming.CharacterEllipsis; title.Margin = new Thickness(SyncWatchTokens.ControlCompactGap, 0, SyncWatchTokens.ControlCompactGap, 0); Grid.SetColumn(title, 1); top.Children.Add(title);
        var right = Row(); right.Children.Add(Text(T(char.ToLowerInvariant(presentation.State.ToString()[0]) + presentation.State.ToString()[1..]), true)); right.Children.Add(Button("openCall", "call")); right.Children.Add(Button("toggleFullscreen", "fullscreen")); right.Children.Add(Button("endWatching", "end")); Grid.SetColumn(right, 2); top.Children.Add(right);
        var header = new Border { Child = top }; header.SetResourceReference(BackgroundProperty, "theme.backgroundDeep.brush"); root.Children.Add(header);
        var video = new Grid(); video.SetResourceReference(BackgroundProperty, "color.shared.videoSurface.brush"); if (VideoSurface is not null) video.Children.Add(VideoSurface); AutomationProperties.SetName(video, T("videoSurface")); Grid.SetRow(video, 1); root.Children.Add(video);
        var footer = new Grid { Margin = new Thickness(SyncWatchTokens.LayoutPanelPadding, 0, SyncWatchTokens.LayoutPanelPadding, 0) };
        footer.RowDefinitions.Add(new() { Height = new GridLength(SyncWatchTokens.ControlPlayerSliderHeight) }); footer.RowDefinitions.Add(new());
        var timeline = new Grid(); timeline.ColumnDefinitions.Add(new() { Width = new GridLength(SyncWatchTokens.LayoutPlayerTimeWidth) }); timeline.ColumnDefinitions.Add(new()); timeline.ColumnDefinitions.Add(new() { Width = new GridLength(SyncWatchTokens.LayoutPlayerTimeWidth) });
        timeline.Children.Add(Text(PlayerPresentation.Time(presentation.DisplayedPosition)));
        var seek = Slider("seek", presentation.DisplayedPosition, Math.Max(1, presentation.DisplayedDuration)); Grid.SetColumn(seek, 1); timeline.Children.Add(seek);
        var duration = Text(PlayerPresentation.Time(presentation.DisplayedDuration)); duration.TextAlignment = TextAlignment.Right; Grid.SetColumn(duration, 2); timeline.Children.Add(duration); footer.Children.Add(timeline);
        var controls = new Grid(); controls.ColumnDefinitions.Add(new()); controls.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); controls.ColumnDefinitions.Add(new()); Grid.SetRow(controls, 1); footer.Children.Add(controls);
        var left = Row(); left.Children.Add(Button("openPlayerSettings", "settings", "playerSettings")); left.Children.Add(Button("openPlaylist", "playlist", "playlist")); controls.Children.Add(left);
        var transport = Row(); transport.Children.Add(Button("previousFile", "previous")); transport.Children.Add(Button("skip", "backward", "skipBackward", -1)); transport.Children.Add(Button("playPause", presentation.Playing ? "pause" : "play", presentation.Playing ? "pause" : "play", prominent: true)); transport.Children.Add(Button("skip", "forward", "skipForward", 1)); transport.Children.Add(Button("nextFile", "next")); Grid.SetColumn(transport, 1); controls.Children.Add(transport);
        var sound = Row(); sound.HorizontalAlignment = HorizontalAlignment.Right;
        sound.Children.Add(Button("selectSubtitles", "subtitles", "subtitles")); sound.Children.Add(Button("selectAudio", "audio", "audioTracks")); sound.Children.Add(Button("muteMovie", presentation.Muted ? "muted" : "volume", presentation.Muted ? "unmuteMovie" : "muteMovie"));
        var volume = Slider("setMovieVolume", presentation.IsValid ? presentation.Volume : 0, 1); volume.Width = SyncWatchTokens.LayoutPlayerVolumeWidth; sound.Children.Add(volume); Grid.SetColumn(sound, 2); controls.Children.Add(sound);
        var bottom = new Border { Child = footer }; bottom.SetResourceReference(BackgroundProperty, "theme.backgroundDeep.brush"); Grid.SetRow(bottom, 2); root.Children.Add(bottom);
    }
    private static StackPanel Row() => new() { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
    private TextBlock Text(string text, bool muted = false)
    {
        var block = new TextBlock { Text = text, VerticalAlignment = VerticalAlignment.Center };
        block.SetResourceReference(TextBlock.ForegroundProperty, muted ? "theme.textSecondary.brush" : "theme.text.brush"); return block;
    }
    private Button Button(string action, string icon, string? label = null, double? value = null, bool prominent = false)
    {
        var geometry = new GeometryGroup();
        foreach (var polygon in SyncWatchPlayer.Icons[icon])
        {
            var figure = new PathFigure { StartPoint = new Point(polygon[0], polygon[1]), IsClosed = true, IsFilled = true };
            for (int i = 2; i < polygon.Length; i += 2) figure.Segments.Add(new LineSegment(new Point(polygon[i], polygon[i + 1]), true));
            geometry.Children.Add(new PathGeometry([figure]));
        }
        var path = new System.Windows.Shapes.Path { Data = geometry, Width = SyncWatchTokens.ControlPlayerIconSize, Height = SyncWatchTokens.ControlPlayerIconSize, Stretch = Stretch.None };
        path.SetResourceReference(System.Windows.Shapes.Shape.FillProperty, prominent ? "color.dark.text.brush" : "theme.text.brush");
        var button = new Button { Content = path, IsEnabled = Presentation.Allows(action), ToolTip = T(label ?? action), Margin = new Thickness(SyncWatchTokens.ControlCompactGap / 2, 0, SyncWatchTokens.ControlCompactGap / 2, 0) };
        button.SetResourceReference(StyleProperty, prominent ? "SyncWatch.PlayerProminentButton" : "SyncWatch.PlayerButton");
        AutomationProperties.SetAutomationId(button, "player." + (label ?? action)); AutomationProperties.SetName(button, T(label ?? action)); button.Click += (_, _) => Emit(action, value); return button;
    }
    private Slider Slider(string action, double value, double maximum)
    {
        var slider = new Slider { Minimum = 0, Maximum = maximum, Value = value, IsEnabled = Presentation.Allows(action), IsSnapToTickEnabled = action == "seek", TickFrequency = action == "seek" ? 1 : 0.01, SmallChange = action == "seek" ? 1000 : 0.05, LargeChange = action == "seek" ? 10000 : 0.1 };
        slider.SetResourceReference(StyleProperty, "SyncWatch.PlayerSlider"); AutomationProperties.SetAutomationId(slider, "player." + action); AutomationProperties.SetName(slider, T(action));
        // Observation-driven initialization happens before subscribing; it emits no user request.
        slider.ValueChanged += (_, e) => Emit(action, action == "seek" ? Math.Round(e.NewValue) : e.NewValue); return slider;
    }
}

public sealed class PlayerGallery : UserControl
{
    private PlayerPresentation presentation = PlayerPresentation.Gallery(PlayerVisualState.Paused);
    private readonly PlayerChrome player = new();
    private readonly TextBlock last = new() { Text = "" };
    private string language = "en";
    public PlayerGallery()
    {
        var root = new DockPanel(); var bar = new StackPanel { Orientation = Orientation.Horizontal, Margin = SyncWatchTokens.ControlCompactGapThickness };
        var states = new ComboBox { ItemsSource = Enum.GetValues<PlayerVisualState>(), SelectedItem = presentation.State, Width = 180 };
        states.SelectionChanged += (_, _) => { presentation = PlayerPresentation.Gallery((PlayerVisualState)states.SelectedItem); Render(); }; bar.Children.Add(states);
        var locales = new ComboBox { ItemsSource = new[] { "en", "ru" }, SelectedIndex = 0, Width = 80 }; locales.SelectionChanged += (_, _) => { language = (string)locales.SelectedItem; Render(); }; bar.Children.Add(locales);
        var themes = new ComboBox { ItemsSource = new[] { "dark", "light" }, SelectedIndex = 0, Width = 100 }; themes.SelectionChanged += (_, _) =>
        {
            var resources = Application.Current.Resources;
            var dictionary = resources.MergedDictionaries.First(d => d.Contains("theme.dark"));
            resources.MergedDictionaries.Add((ResourceDictionary)dictionary["theme." + themes.SelectedItem]);
        }; bar.Children.Add(themes); bar.Children.Add(last); DockPanel.SetDock(bar, Dock.Top); root.Children.Add(bar); root.Children.Add(player); Content = root;
        player.VideoSurface = new TextBlock { Text = SyncWatchCopy.Text("playerFixture"), Foreground = Brushes.White, VerticalAlignment = VerticalAlignment.Center, HorizontalAlignment = HorizontalAlignment.Center };
        player.ActionRequested += (action, value) =>
        {
            last.Text = action + (value is double v ? ": " + v.ToString(CultureInfo.InvariantCulture) : "");
            presentation = action switch
            {
                "seek" => presentation with { PositionMs = (long)(value ?? 0) },
                "playPause" => presentation with { State = presentation.Playing ? PlayerVisualState.Paused : PlayerVisualState.Playing },
                "setMovieVolume" => presentation with { Volume = value ?? 0 },
                "muteMovie" => presentation with { Muted = !presentation.Muted },
                _ => presentation,
            }; Render();
        }; Render();
    }
    private void Render()
    {
        if (player.VideoSurface is TextBlock fixture) fixture.Text = SyncWatchCopy.Text("playerFixture", language);
        player.Render(presentation, language);
    }
}
