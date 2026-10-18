using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;

namespace SyncWatch.Design;

public enum LibraryVisualState { Empty, Scanning, Selected, MissingMedia, Reconnecting }

public sealed record LibraryEntry(string Id, string Title, string Location);

// Presentation/capabilities only: no filesystem, media engine, call or network dependency.
public sealed record LibraryPresentation
{
    public LibraryVisualState State { get; init; }
    public IReadOnlyList<LibraryEntry> Entries { get; init; } = [];
    public string? SelectedId { get; init; }
    public IReadOnlySet<string> EnabledActions { get; init; } = new HashSet<string>();
    public LibraryEntry? Selected => Entries.FirstOrDefault(e => e.Id == SelectedId);

    public bool Allows(string action) => EnabledActions.Contains(action) && SyncWatchCopy.LibraryActions.Contains(action) && (action switch
    {
        "startWatching" => State == LibraryVisualState.Selected && Selected is not null,
        "selectMovie" or "search" => State != LibraryVisualState.Scanning,
        _ => true,
    });

    public void Dispatch(string action, string? value, Action<string, string?> handler)
    {
        if (Allows(action) && (action != "selectMovie" || Entries.Any(e => e.Id == value))) handler(action, value);
    }

    public static LibraryPresentation Gallery(LibraryVisualState state)
    {
        LibraryEntry[] entries = state is LibraryVisualState.Empty or LibraryVisualState.Scanning ? [] :
            SyncWatchCopy.GalleryMovies.Select((title, index) => new LibraryEntry(index.ToString(System.Globalization.CultureInfo.InvariantCulture), title, "Movies/" + title)).ToArray();
        return new LibraryPresentation
        {
            State = state,
            Entries = entries,
            SelectedId = entries.FirstOrDefault()?.Id,
            EnabledActions = new HashSet<string> { "chooseFolder", "rescan", "search", "selectMovie", "startWatching", "openSettings" },
        };
    }
}

public sealed class LibraryWorkspace : UserControl
{
    public LibraryPresentation Presentation { get; private set; } = new();
    public string Language { get; private set; } = "en";
    public event Action<string, string?>? ActionRequested;
    private readonly Grid root = new();
    private readonly Grid content = new();
    private readonly RowDefinition selectedRow = new();
    private readonly StackPanel rows = new();
    private string query = "";
    private readonly List<UniformGrid> metricGrids = [];

    public LibraryWorkspace()
    {
        FontSize = SyncWatchTokens.TypeBodySize;
        SetResourceReference(ForegroundProperty, "theme.text.brush");
        SetResourceReference(BackgroundProperty, "SyncWatch.WorkspaceBackground");
        Content = root;
        SizeChanged += (_, e) =>
        {
            ResizeDetails();
            foreach (var metrics in metricGrids) metrics.Columns = e.NewSize.Width < 1000 ? 2 : 4;
        };
        Render(new());
    }

    public void Render(LibraryPresentation presentation, string language = "en")
    {
        Presentation = presentation;
        Language = language;
        query = "";
        metricGrids.Clear();
        root.Children.Clear(); root.RowDefinitions.Clear();
        root.Margin = SyncWatchTokens.LayoutWorkspacePaddingThickness;
        root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(SyncWatchTokens.LayoutHeaderHeight) });
        root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(SyncWatchTokens.LayoutPanelGap) });
        root.RowDefinitions.Add(new RowDefinition());
        root.Children.Add(Header());
        var columns = new Grid();
        columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(SyncWatchTokens.LayoutLibraryPanelWidth) });
        columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(SyncWatchTokens.LayoutPanelGap) });
        columns.ColumnDefinitions.Add(new ColumnDefinition());
        Grid.SetRow(columns, 2); root.Children.Add(columns);
        columns.Children.Add(Library());
        content.Children.Clear(); content.RowDefinitions.Clear();
        content.RowDefinitions.Add(selectedRow);
        content.RowDefinitions.Add(new RowDefinition { Height = new GridLength(SyncWatchTokens.LayoutPanelGap) });
        content.RowDefinitions.Add(new RowDefinition());
        Grid.SetColumn(content, 2); columns.Children.Add(content);
        content.Children.Add(Details());
        var lower = new Grid();
        lower.ColumnDefinitions.Add(new ColumnDefinition());
        lower.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(SyncWatchTokens.LayoutPanelGap) });
        lower.ColumnDefinitions.Add(new ColumnDefinition());
        lower.Children.Add(Information("roomStatus", presentation.State == LibraryVisualState.Reconnecting ? "reconnecting" : "disconnected"));
        var activity = Information("recentActivity", "noActivity"); Grid.SetColumn(activity, 2); lower.Children.Add(activity);
        Grid.SetRow(lower, 2); content.Children.Add(lower);
        ResizeDetails();
    }

    private string T(string key) => SyncWatchCopy.Text(key, Language);
    private void Emit(string action, string? value = null) => Presentation.Dispatch(action, value, (a, v) => ActionRequested?.Invoke(a, v));
    private void ResizeDetails() => selectedRow.Height = new GridLength(Math.Clamp(
        ActualHeight - SyncWatchTokens.LayoutWorkspacePadding * 2 - SyncWatchTokens.LayoutHeaderHeight - SyncWatchTokens.LayoutPanelGap * 2 - SyncWatchTokens.LayoutLowerPanelMinHeight,
        SyncWatchTokens.LayoutSelectedPanelMinHeight, SyncWatchTokens.LayoutSelectedPanelMaxHeight));

    private Border Panel(UIElement child, double padding = 0)
    {
        var panel = new Border { Child = child, Padding = new Thickness(padding), CornerRadius = SyncWatchTokens.LayoutPanelRadiusCornerRadius, BorderThickness = SyncWatchTokens.ControlBorderWidthThickness };
        panel.SetResourceReference(Border.BackgroundProperty, "theme.surface.brush");
        panel.SetResourceReference(Border.BorderBrushProperty, "theme.border.brush");
        return panel;
    }

    private TextBlock Text(string value, bool muted = false, double? size = null, bool bold = false)
    {
        var text = new TextBlock { Text = value, FontSize = size ?? SyncWatchTokens.TypeBodySize, TextWrapping = TextWrapping.Wrap, FontWeight = bold ? FontWeights.Bold : FontWeights.Normal };
        text.SetResourceReference(TextBlock.ForegroundProperty, muted ? "theme.textSecondary.brush" : "theme.text.brush");
        return text;
    }

    private Button Button(string action, bool filled = false)
    {
        var button = new Button { Content = T(action), IsEnabled = Presentation.Allows(action), Margin = new Thickness(0, 0, SyncWatchTokens.ControlCompactGap, 0) };
        button.SetResourceReference(StyleProperty, filled ? "SyncWatch.FilledButton" : "SyncWatch.OutlinedButton");
        AutomationProperties.SetAutomationId(button, "library." + action);
        button.Click += (_, _) => Emit(action);
        return button;
    }

    private Border Header()
    {
        var header = new DockPanel { LastChildFill = false };
        var mark = new System.Windows.Shapes.Polygon { Points = new PointCollection { new(5, 3), new(17, 10), new(5, 17) }, Width = SyncWatchTokens.ControlIconSize, Height = SyncWatchTokens.ControlIconSize, Fill = Brushes.White };
        var logo = new Border { Child = mark, Width = SyncWatchTokens.ControlBrandSize, Height = SyncWatchTokens.ControlBrandSize, CornerRadius = SyncWatchTokens.ControlButtonRadiusCornerRadius, VerticalAlignment = VerticalAlignment.Center };
        logo.SetResourceReference(Border.BackgroundProperty, "theme.accent.brush");
        header.Children.Add(logo);
        var settings = Button("openSettings"); DockPanel.SetDock(settings, Dock.Right); header.Children.Add(settings);
        var brand = Text(T("brand"), size: SyncWatchTokens.TypeBrandSize, bold: true); brand.VerticalAlignment = VerticalAlignment.Center; brand.Margin = SyncWatchTokens.LayoutPanelPaddingThickness; header.Children.Add(brand);
        var room = Text(T("room")); room.VerticalAlignment = VerticalAlignment.Center; header.Children.Add(room);
        var status = Text(T("callInactive"), true); status.VerticalAlignment = VerticalAlignment.Center; status.Margin = SyncWatchTokens.LayoutPanelPaddingThickness; DockPanel.SetDock(status, Dock.Right); header.Children.Add(status);
        return Panel(header, SyncWatchTokens.ControlCompactGap);
    }

    private Border Library()
    {
        var dock = new DockPanel();
        var top = new StackPanel(); DockPanel.SetDock(top, Dock.Top); dock.Children.Add(top);
        top.Children.Add(Text(T("library") + "  ·  " + Presentation.Entries.Count + " " + T("files"), size: SyncWatchTokens.TypeSectionSize, bold: true));
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, SyncWatchTokens.LayoutPanelGap, 0, SyncWatchTokens.LayoutPanelGap) };
        actions.Children.Add(Button("chooseFolder")); actions.Children.Add(Button("rescan")); top.Children.Add(actions);
        var search = new TextBox { IsEnabled = Presentation.Allows("search"), ToolTip = T("search"), Margin = new Thickness(0, 0, 0, SyncWatchTokens.LayoutPanelGap) };
        search.SetResourceReference(StyleProperty, "SyncWatch.Field"); AutomationProperties.SetName(search, T("search")); AutomationProperties.SetAutomationId(search, "library.search");
        search.TextChanged += (_, _) => { query = search.Text; PopulateRows(); Emit("search", query); }; top.Children.Add(search);
        rows.Children.Clear();
        dock.Children.Add(new ScrollViewer { Content = rows, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Auto });
        PopulateRows(); return Panel(dock, SyncWatchTokens.LayoutPanelPadding);
    }

    private void PopulateRows()
    {
        rows.Children.Clear();
        if (Presentation.Entries.Count == 0) { rows.Children.Add(Text(T(Presentation.State == LibraryVisualState.Scanning ? "scanning" : "empty"), true)); return; }
        foreach (var entry in Presentation.Entries.Where(e => e.Title.Contains(query, StringComparison.CurrentCultureIgnoreCase)))
        {
            var row = new Button
            {
                Content = Text(entry.Title),
                MinHeight = SyncWatchTokens.ControlRowMinHeight,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
                Margin = new Thickness(0, 0, 0, SyncWatchTokens.ControlCompactGap),
                IsEnabled = Presentation.Allows("selectMovie")
            };
            row.SetResourceReference(StyleProperty, "SyncWatch.OutlinedButton");
            if (entry.Id == Presentation.SelectedId) row.SetResourceReference(BackgroundProperty, "theme.selection.brush");
            AutomationProperties.SetAutomationId(row, "library.movie." + entry.Id);
            row.Click += (_, _) => Emit("selectMovie", entry.Id);
            rows.Children.Add(row);
        }
    }

    private Border Details()
    {
        if (Presentation.Selected is not { } entry) return Panel(new TextBlock { Text = T("selectMovie"), HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center });
        var stack = new StackPanel();
        stack.Children.Add(Text(T("selectedMovie"), true));
        stack.Children.Add(Text(entry.Title, size: SyncWatchTokens.TypeTitleSize, bold: true));
        var metrics = new UniformGrid { Columns = ActualWidth < 1000 ? 2 : 4, Margin = new Thickness(0, SyncWatchTokens.LayoutPanelGap, 0, SyncWatchTokens.LayoutPanelGap) };
        foreach (var key in new[] { "duration", "resolution", "audio", "subtitles" }) { var metric = new StackPanel(); metric.Children.Add(Text(T(key), true)); metric.Children.Add(Text(T("unknown"), bold: true)); metrics.Children.Add(metric); }
        metricGrids.Add(metrics);
        stack.Children.Add(metrics);
        if (Presentation.State == LibraryVisualState.MissingMedia) stack.Children.Add(Text(T("missingMedia"), true));
        var actions = new WrapPanel(); actions.Children.Add(Button("startWatching", true)); actions.Children.Add(Button("continueWatching")); actions.Children.Add(Button("endWatching")); stack.Children.Add(actions);
        var location = new StackPanel { Margin = new Thickness(0, SyncWatchTokens.LayoutPanelGap, 0, 0) }; location.Children.Add(Text(T("fileLocation"))); location.Children.Add(Text(entry.Location, true)); stack.Children.Add(location);
        return Panel(new ScrollViewer { Content = stack, VerticalScrollBarVisibility = ScrollBarVisibility.Auto }, SyncWatchTokens.LayoutDetailPadding);
    }

    private Border Information(string title, string message)
    {
        var stack = new StackPanel(); stack.Children.Add(Text(T(title), size: SyncWatchTokens.TypeSectionSize, bold: true));
        var body = Text(T(message), true); body.Margin = new Thickness(0, SyncWatchTokens.LayoutPanelGap, 0, SyncWatchTokens.LayoutPanelGap); stack.Children.Add(body);
        if (title == "roomStatus") stack.Children.Add(Button("openCall"));
        return Panel(stack, SyncWatchTokens.LayoutPanelPadding);
    }
}

public sealed class DesignGallery : DockPanel
{
    public LibraryWorkspace Workspace { get; } = new();
    public DesignGallery()
    {
        var toolbar = new StackPanel { Orientation = Orientation.Horizontal, Margin = SyncWatchTokens.LayoutPanelPaddingThickness };
        var states = new ComboBox { ItemsSource = SyncWatchCopy.GalleryStates, SelectedIndex = 2 };
        var languages = new ComboBox { ItemsSource = new[] { "en", "ru" }, SelectedIndex = 0 };
        var themes = new ComboBox { ItemsSource = new[] { "dark", "light" }, SelectedIndex = 0 };
        toolbar.Children.Add(states); toolbar.Children.Add(languages); toolbar.Children.Add(themes);
        DockPanel.SetDock(toolbar, Dock.Top); Children.Add(toolbar); Children.Add(Workspace);
        void Refresh() => Workspace.Render(LibraryPresentation.Gallery(Enum.Parse<LibraryVisualState>((string)states.SelectedItem, true)), (string)languages.SelectedItem);
        states.SelectionChanged += (_, _) => Refresh(); languages.SelectionChanged += (_, _) => Refresh();
        themes.SelectionChanged += (_, _) =>
        {
            Resources.MergedDictionaries.Clear();
            var source = Application.Current.Resources.MergedDictionaries[0];
            Resources.MergedDictionaries.Add((ResourceDictionary)source["theme." + themes.SelectedItem]);
        };
        Workspace.ActionRequested += (action, value) => { if (action == "selectMovie") Workspace.Render(Workspace.Presentation with { SelectedId = value }, Workspace.Language); };
        Resources.MergedDictionaries.Add((ResourceDictionary)Application.Current.Resources.MergedDictionaries[0]["theme.dark"]);
        Refresh();
    }
}
