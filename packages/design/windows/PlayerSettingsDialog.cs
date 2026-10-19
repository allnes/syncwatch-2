using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Shapes;

namespace SyncWatch.Design;

public enum PlayerSettingsVisualState { Editing, SavedNotice, InvalidConfiguration, ReadOnly }

public sealed class PlayerSettingsEditor
{
    private Dictionary<string, string> values;
    private Dictionary<string, string> original;
    public IReadOnlyDictionary<string, string> Values => new ReadOnlyDictionary<string, string>(new Dictionary<string, string>(values));
    public IReadOnlySet<string> EditableFields { get; }
    public bool CanSave { get; }
    public PlayerSettingsVisualState State { get; private set; }
    public string Message { get; private set; } = "";
    public PlayerSettingsEditor(IReadOnlyDictionary<string, string>? initial = null, IEnumerable<string>? editableFields = null,
        bool canSave = false, PlayerSettingsVisualState state = PlayerSettingsVisualState.Editing)
    {
        values = new(SyncWatchPlayerSettings.Defaults); foreach (var pair in initial ?? new Dictionary<string, string>()) values[pair.Key] = pair.Value;
        original = new(values); EditableFields = new HashSet<string>(editableFields ?? []); CanSave = canSave && state != PlayerSettingsVisualState.ReadOnly; State = CanSave ? state : PlayerSettingsVisualState.ReadOnly;
        if (State == PlayerSettingsVisualState.InvalidConfiguration) Message = "invalidConfiguration";
        if (State == PlayerSettingsVisualState.SavedNotice) Message = "changesSaved";
    }
    public bool Allows(string id) => CanSave && EditableFields.Contains(id) && SyncWatchPlayerSettings.Fields.Any(f => f.Id == id);
    public void Edit(string id, string value) { if (Allows(id)) { values[id] = value; State = PlayerSettingsVisualState.Editing; Message = ""; } }
    public static bool Valid(string value, PlayerSettingField descriptor)
    {
        if (value.Length > 64 || value.Any(c => c < 32 || c is >= (char)127 and <= (char)159)) return false;
        if (descriptor.Kind == "boolean") return value is "true" or "false";
        if (descriptor.Kind != "range") return descriptor.Options.Any(o => o.Id == value);
        if (!Regex.IsMatch(value, @"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$", RegexOptions.CultureInvariant)
            || !double.TryParse(value, NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture, out var number)
            || !double.IsFinite(number) || number < descriptor.Minimum || number > descriptor.Maximum) return false;
        double ticks = (number - descriptor.Minimum) / descriptor.Step; return Math.Abs(ticks - Math.Round(ticks)) < 1e-8;
    }
    public bool IsValid => values.Keys.ToHashSet().SetEquals(SyncWatchPlayerSettings.Defaults.Keys) && EditableFields.All(SyncWatchPlayerSettings.Defaults.ContainsKey)
        && SyncWatchPlayerSettings.Fields.All(f => values.TryGetValue(f.Id, out var value) && Valid(value, f));
    public bool CanReset(string section) => SyncWatchPlayerSettings.Sections.Contains(section) && SyncWatchPlayerSettings.Fields.Any(f => f.Section == section && Allows(f.Id));
    public void Reset(string section)
    {
        if (!CanReset(section)) return;
        foreach (var descriptor in SyncWatchPlayerSettings.Fields.Where(f => f.Section == section && Allows(f.Id))) values[descriptor.Id] = SyncWatchPlayerSettings.Defaults[descriptor.Id];
        State = PlayerSettingsVisualState.Editing; Message = "";
    }
    public bool Save(Func<IReadOnlyDictionary<string, string>, bool> persist)
    {
        if (!CanSave) return false;
        if (!IsValid) { State = PlayerSettingsVisualState.InvalidConfiguration; Message = "invalidConfiguration"; return false; }
        if (!persist(Values)) { State = PlayerSettingsVisualState.InvalidConfiguration; Message = "saveFailed"; return false; }
        original = new(values); State = PlayerSettingsVisualState.SavedNotice; Message = "changesSaved"; return true;
    }
    public void Cancel() { values = new(original); State = CanSave ? PlayerSettingsVisualState.Editing : PlayerSettingsVisualState.ReadOnly; Message = ""; }
    public static string Canonical(double value) => double.IsFinite(value) ? (Math.Abs(value) < 1e-8 ? 0 : value).ToString("0.##", CultureInfo.InvariantCulture) : "";
}

public sealed class PlayerSubtitlePreview : FrameworkElement
{
    public PlayerSettingsEditor Editor { get; }
    public string UiLanguage { get; }
    public PlayerSubtitlePreview(PlayerSettingsEditor editor, string language = "en")
    {
        Editor = editor; UiLanguage = language; Height = SyncWatchTokens.LayoutPlayerSettingsPreviewHeight; ClipToBounds = true;
        AutomationProperties.SetName(this, SyncWatchCopy.Text("subtitlePreview", language));
    }
    private string Setting(string id)
    {
        var descriptor = SyncWatchPlayerSettings.Fields.Single(f => f.Id == id); string value = Editor.Values[id];
        return PlayerSettingsEditor.Valid(value, descriptor) ? value : SyncWatchPlayerSettings.Defaults[id];
    }
    private double Number(string id) => double.Parse(Setting(id), CultureInfo.InvariantCulture);
    protected override void OnRender(DrawingContext drawing)
    {
        base.OnRender(drawing); drawing.DrawRectangle(new SolidColorBrush(SyncWatchTokens.ColorSharedVideoSurface), null, new Rect(RenderSize));
        double size = Number("subtitleSize"), padding = Number("subtitlePadding"); bool top = Setting("subtitlePosition") == "top";
        string family = Setting("subtitleFont") switch { "serif" => "Global Serif", "monospace" => "Global Monospace", _ => "Global User Interface" };
        var typeface = new Typeface(new FontFamily(family), FontStyles.Normal, FontWeights.Bold, FontStretches.Normal);
        var fill = new SolidColorBrush(SyncWatchPlayerSettings.Color(Setting("subtitleColor")) ?? SyncWatchTokens.ColorSubtitleWhite);
        var outline = new SolidColorBrush(SyncWatchPlayerSettings.Color(Setting("outlineColor")) ?? SyncWatchTokens.ColorSubtitleBlack);
        var text = new FormattedText(SyncWatchCopy.Text("subtitlePreview", UiLanguage), CultureInfo.GetCultureInfo(UiLanguage), FlowDirection.LeftToRight, typeface, size, fill, VisualTreeHelper.GetDpi(this).PixelsPerDip)
        {
            MaxTextWidth = Math.Max(1, ActualWidth - padding * 2),
            MaxLineCount = 2,
            TextAlignment = TextAlignment.Center,
        };
        var geometry = text.BuildGeometry(new Point());
        double baseline = top ? padding + size / 2 : ActualHeight - padding - size / 2;
        double position = Math.Clamp(baseline + Number("subtitleOffset") / 120 * ActualHeight * 0.34 * (top ? 1 : -1), size / 2, ActualHeight - size / 2);
        geometry.Transform = new TranslateTransform((ActualWidth - geometry.Bounds.Width) / 2 - geometry.Bounds.X, position - geometry.Bounds.Height / 2 - geometry.Bounds.Y);
        drawing.DrawGeometry(fill, new Pen(outline, Number("outlineWidth")), geometry);
    }
}

public sealed class PlayerSettingsDialog : UserControl
{
    public PlayerSettingsEditor Editor { get; }
    public string UiLanguage { get; }
    public string Section { get; private set; }
    public Func<IReadOnlyDictionary<string, string>, bool> Persist { get; set; } = _ => false;
    public event Action? CloseRequested;
    public event Action? MoveRequested;
    private readonly Grid root = new();
    private TextBlock status = new();
    private PlayerSubtitlePreview? preview;
    private readonly List<(Button Button, string Field, string Option)> swatches = [];
    public PlayerSettingsDialog(PlayerSettingsEditor? editor = null, string language = "en", string section = "playback")
    {
        Editor = editor ?? new(); UiLanguage = language; Section = SyncWatchPlayerSettings.Sections.Contains(section) ? section : "playback";
        Language = System.Windows.Markup.XmlLanguage.GetLanguage(language); Width = SyncWatchTokens.LayoutSettingsWidth; Height = SyncWatchTokens.LayoutPlayerSettingsHeight;
        FontSize = SyncWatchTokens.TypeSettingsBodySize; SetResourceReference(ForegroundProperty, "theme.text.brush");
        Clip = new RectangleGeometry(new Rect(0, 0, Width, Height), SyncWatchTokens.ControlCompactDialogRadius, SyncWatchTokens.ControlCompactDialogRadius);
        var border = new Border { Child = root, CornerRadius = SyncWatchTokens.ControlCompactDialogRadiusCornerRadius, BorderThickness = SyncWatchTokens.ControlBorderWidthThickness };
        border.SetResourceReference(Border.BackgroundProperty, "theme.surface.brush"); border.SetResourceReference(Border.BorderBrushProperty, "theme.border.brush"); Content = border;
        KeyboardNavigation.SetTabNavigation(this, KeyboardNavigationMode.Cycle); Render();
    }
    private string T(string key) => key.Length == 0 ? "" : SyncWatchCopy.Text(key, UiLanguage);
    private TextBlock Text(string value, bool muted = false)
    {
        var text = new TextBlock { Text = value, TextWrapping = TextWrapping.Wrap }; text.SetResourceReference(TextBlock.ForegroundProperty, muted ? "theme.textSecondary.brush" : "theme.text.brush"); return text;
    }
    private Button Button(string id, Action clicked, bool enabled = true, bool filled = false)
    {
        var button = new Button { Content = T(id), IsEnabled = enabled, Margin = new Thickness(SyncWatchTokens.ControlCompactGap, 0, 0, 0) };
        button.SetResourceReference(StyleProperty, filled ? "SyncWatch.SettingsFilledButton" : "SyncWatch.SettingsButton"); AutomationProperties.SetAutomationId(button, "playerSettings." + id); button.Click += (_, _) => clicked(); return button;
    }
    private Border Line() { var line = new Border { Height = SyncWatchTokens.ControlBorderWidth }; line.SetResourceReference(Border.BackgroundProperty, "theme.border.brush"); return line; }
    private void Close() { Editor.Cancel(); CloseRequested?.Invoke(); }
    public void SelectSection(string section) { if (SyncWatchPlayerSettings.Sections.Contains(section)) { Section = section; Render(); } }
    private void Render()
    {
        root.Children.Clear(); root.RowDefinitions.Clear(); swatches.Clear(); preview = null;
        foreach (double height in new[] { SyncWatchTokens.LayoutSettingsHeaderHeight, 1, -1, 1, SyncWatchTokens.LayoutSettingsFooterHeight }) root.RowDefinitions.Add(new() { Height = height < 0 ? new GridLength(1, GridUnitType.Star) : new GridLength(height) });
        var header = new DockPanel { Margin = new Thickness(SyncWatchTokens.LayoutSettingsCardPadding, 0, SyncWatchTokens.LayoutSettingsCardPadding, 0) };
        var close = Button("close", Close); close.TabIndex = 0; close.VerticalAlignment = VerticalAlignment.Center; DockPanel.SetDock(close, Dock.Right); header.Children.Add(close);
        var title = Text(T("playerSettings")); title.FontWeight = FontWeights.Bold; title.FontSize = SyncWatchTokens.TypeSettingsTitleSize; title.VerticalAlignment = VerticalAlignment.Center;
        title.MouseLeftButtonDown += (_, e) => { if (e.ButtonState == MouseButtonState.Pressed) MoveRequested?.Invoke(); }; header.Children.Add(title);
        var top = new Border { Child = header }; top.SetResourceReference(Border.BackgroundProperty, "theme.backgroundDeep.brush"); root.Children.Add(top);
        var topLine = Line(); Grid.SetRow(topLine, 1); root.Children.Add(topLine);
        var body = new Grid(); body.ColumnDefinitions.Add(new() { Width = new GridLength(SyncWatchTokens.LayoutPlayerSettingsSidebarWidth) }); body.ColumnDefinitions.Add(new() { Width = new GridLength(1) }); body.ColumnDefinitions.Add(new()); Grid.SetRow(body, 2); root.Children.Add(body);
        var tabs = new StackPanel { Margin = SyncWatchTokens.LayoutSettingsCardPaddingThickness };
        foreach (string section in SyncWatchPlayerSettings.Sections)
        {
            var button = Button(section, () => SelectSection(section)); button.Margin = new Thickness(0, 0, 0, 1); button.Height = SyncWatchTokens.LayoutSettingsSidebarRowHeight; button.TabIndex = 1 + Array.IndexOf(SyncWatchPlayerSettings.Sections, section); button.HorizontalContentAlignment = HorizontalAlignment.Left;
            button.SetResourceReference(StyleProperty, "SyncWatch.SettingsTab"); button.SetResourceReference(BackgroundProperty, section == Section ? "theme.selection.brush" : "theme.backgroundDeep.brush"); AutomationProperties.SetAutomationId(button, "playerSettings.section." + section); tabs.Children.Add(button);
        }
        var sidebar = new Border { Child = tabs }; sidebar.SetResourceReference(Border.BackgroundProperty, "theme.backgroundDeep.brush"); body.Children.Add(sidebar);
        var vertical = new Border(); vertical.SetResourceReference(Border.BackgroundProperty, "theme.border.brush"); Grid.SetColumn(vertical, 1); body.Children.Add(vertical);
        var content = new StackPanel { Margin = SyncWatchTokens.LayoutSettingsContentPaddingThickness };
        var sectionHeader = new DockPanel(); var reset = Button("resetSection", () => { Editor.Reset(Section); Render(); }, Editor.CanReset(Section)); reset.TabIndex = 8; DockPanel.SetDock(reset, Dock.Right); sectionHeader.Children.Add(reset);
        var heading = Text(T(Section)); heading.FontSize = SyncWatchTokens.TypeSettingsSectionSize; heading.FontWeight = FontWeights.Bold; sectionHeader.Children.Add(heading); content.Children.Add(sectionHeader);
        var hint = Text(T(Section + "Hint"), true); hint.Margin = new Thickness(0, SyncWatchTokens.ControlCompactGap, 0, SyncWatchTokens.ControlCompactGap); content.Children.Add(hint);
        var fields = new StackPanel();
        foreach (var group in SyncWatchPlayerSettings.Fields.Where(f => f.Section == Section).GroupBy(f => f.Row).OrderBy(g => g.Key))
        {
            var row = new Grid { Margin = new Thickness(0, 0, 0, SyncWatchTokens.ControlCompactGap) }; int column = 0;
            foreach (var descriptor in group)
            {
                row.ColumnDefinitions.Add(new()); var input = Field(descriptor); if (column > 0) input.Margin = new Thickness(SyncWatchTokens.ControlCompactGap, 0, 0, 0); Grid.SetColumn(input, column++); row.Children.Add(input);
            }
            fields.Children.Add(row);
        }
        if (Section == "subtitles") { preview = new PlayerSubtitlePreview(Editor, UiLanguage); fields.Children.Add(preview); }
        var card = new Border { Child = fields, Padding = SyncWatchTokens.LayoutPlayerSettingsCardPaddingThickness, CornerRadius = SyncWatchTokens.LayoutPlayerSettingsCardRadiusCornerRadius, BorderThickness = SyncWatchTokens.ControlBorderWidthThickness };
        card.SetResourceReference(Border.BackgroundProperty, "theme.surface.brush"); card.SetResourceReference(Border.BorderBrushProperty, "theme.border.brush"); content.Children.Add(card);
        var scroll = new ScrollViewer { Content = content, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled }; Grid.SetColumn(scroll, 2); body.Children.Add(scroll);
        var bottomLine = Line(); Grid.SetRow(bottomLine, 3); root.Children.Add(bottomLine);
        var footer = new DockPanel { Margin = new Thickness(SyncWatchTokens.LayoutSettingsCardPadding, 0, SyncWatchTokens.LayoutSettingsCardPadding, 0) };
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center }; var cancel = Button("cancel", Close); cancel.IsCancel = true; cancel.TabIndex = 100;
        var save = Button("save", () => { Editor.Save(Persist); Update(); }, Editor.CanSave, true); save.IsDefault = true; save.TabIndex = 101; buttons.Children.Add(cancel); buttons.Children.Add(save); DockPanel.SetDock(buttons, Dock.Right); footer.Children.Add(buttons);
        status = Text(""); status.FontSize = SyncWatchTokens.TypeCaptionSize; status.VerticalAlignment = VerticalAlignment.Center; AutomationProperties.SetAutomationId(status, "playerSettings.status"); footer.Children.Add(status); Grid.SetRow(footer, 4); root.Children.Add(footer); Update();
    }
    private void Update()
    {
        status.Text = T(Editor.CanSave ? Editor.Message : "settingsReadOnly"); status.SetResourceReference(TextBlock.ForegroundProperty, Editor.State == PlayerSettingsVisualState.SavedNotice ? "theme.success.brush" : "theme.textSecondary.brush");
        preview?.InvalidateVisual();
        foreach (var (button, field, option) in swatches) button.SetResourceReference(BorderBrushProperty, Editor.Values[field] == option ? "theme.accent.brush" : "theme.border.brush");
    }
    private FrameworkElement Field(PlayerSettingField descriptor)
    {
        var stack = new StackPanel(); FrameworkElement input;
        if (descriptor.Kind == "boolean")
        {
            var toggle = new CheckBox { Content = T(descriptor.Label), IsChecked = Editor.Values[descriptor.Id] == "true", MinHeight = SyncWatchTokens.LayoutSettingsControlHeight };
            toggle.SetResourceReference(StyleProperty, "SyncWatch.SettingsToggle"); toggle.SetResourceReference(ForegroundProperty, "theme.text.brush"); toggle.Checked += (_, _) => { Editor.Edit(descriptor.Id, "true"); Update(); }; toggle.Unchecked += (_, _) => { Editor.Edit(descriptor.Id, "false"); Update(); }; input = toggle;
        }
        else
        {
            var label = new DockPanel(); TextBlock? current = null;
            if (descriptor.Kind == "range") { current = Text(Editor.Values[descriptor.Id] + (descriptor.Unit == "unitNone" ? "" : " " + T(descriptor.Unit))); DockPanel.SetDock(current, Dock.Right); label.Children.Add(current); }
            label.Children.Add(Text(T(descriptor.Label), true)); stack.Children.Add(label);
            if (descriptor.Kind == "range")
            {
                string raw = Editor.Values[descriptor.Id]; double initial = double.Parse(PlayerSettingsEditor.Valid(raw, descriptor) ? raw : SyncWatchPlayerSettings.Defaults[descriptor.Id], CultureInfo.InvariantCulture);
                var slider = new Slider { Minimum = descriptor.Minimum, Maximum = descriptor.Maximum, Value = initial, TickFrequency = descriptor.Step, IsSnapToTickEnabled = true, SmallChange = descriptor.Step, LargeChange = descriptor.Step * 2 };
                slider.SetResourceReference(StyleProperty, "SyncWatch.PlayerSlider"); slider.ValueChanged += (_, e) => { Editor.Edit(descriptor.Id, PlayerSettingsEditor.Canonical(descriptor.Minimum + Math.Round((e.NewValue - descriptor.Minimum) / descriptor.Step, MidpointRounding.AwayFromZero) * descriptor.Step)); current!.Text = Editor.Values[descriptor.Id] + (descriptor.Unit == "unitNone" ? "" : " " + T(descriptor.Unit)); Update(); }; input = slider;
            }
            else if (descriptor.Kind == "color")
            {
                var row = new StackPanel { Orientation = Orientation.Horizontal };
                foreach (var option in descriptor.Options)
                {
                    var color = new Ellipse { Width = SyncWatchTokens.LayoutPlayerSettingsColorSize, Height = SyncWatchTokens.LayoutPlayerSettingsColorSize }; color.SetResourceReference(Shape.FillProperty, option.ColorToken + ".brush");
                    var button = new Button { Content = color, Width = SyncWatchTokens.LayoutSettingsControlHeight, Height = SyncWatchTokens.LayoutSettingsControlHeight, Padding = new Thickness(0), ToolTip = T(option.Label), Margin = new Thickness(0, 0, SyncWatchTokens.ControlCompactGap, 0) }; button.SetResourceReference(StyleProperty, "SyncWatch.SettingsButton"); AutomationProperties.SetName(button, T(option.Label)); AutomationProperties.SetAutomationId(button, "playerSettings.color." + option.Id);
                    button.Click += (_, _) => { Editor.Edit(descriptor.Id, option.Id); Update(); }; swatches.Add((button, descriptor.Id, option.Id)); row.Children.Add(button);
                }
                input = row;
            }
            else
            {
                var choice = new ComboBox { ItemsSource = descriptor.Options.Select(o => new KeyValuePair<string, string>(o.Id, T(o.Label))).ToArray(), SelectedValuePath = "Key", DisplayMemberPath = "Value", SelectedValue = Editor.Values[descriptor.Id], MinHeight = SyncWatchTokens.LayoutSettingsControlHeight }; choice.SetResourceReference(StyleProperty, "SyncWatch.SettingsChoice"); choice.SelectionChanged += (_, _) => { if (choice.SelectedValue is string selected) { Editor.Edit(descriptor.Id, selected); Update(); } }; input = choice;
            }
        }
        input.IsEnabled = Editor.Allows(descriptor.Id); if (input is Control control) control.TabIndex = 10 + Array.FindIndex(SyncWatchPlayerSettings.Fields, f => f.Id == descriptor.Id);
        AutomationProperties.SetAutomationId(input, "playerSettings.field." + descriptor.Id); AutomationProperties.SetName(input, T(descriptor.Label)); stack.Children.Add(input); return stack;
    }
}

public sealed class PlayerSettingsGallery : DockPanel
{
    public PlayerSettingsGallery()
    {
        var toolbar = new StackPanel { Orientation = Orientation.Horizontal, Margin = SyncWatchTokens.ControlCompactGapThickness };
        var sections = new ComboBox { ItemsSource = SyncWatchPlayerSettings.Sections, SelectedIndex = 0 };
        var states = new ComboBox { ItemsSource = SyncWatchPlayerSettings.States, SelectedIndex = 0 };
        var locales = new ComboBox { ItemsSource = new[] { "en", "ru" }, SelectedIndex = 0 };
        var themes = new ComboBox { ItemsSource = new[] { "dark", "light" }, SelectedIndex = 0 };
        var fail = new CheckBox { Content = "Fail save" };
        foreach (var item in new UIElement[] { sections, states, locales, themes, fail }) toolbar.Children.Add(item);
        SetDock(toolbar, Dock.Top); Children.Add(toolbar); var container = new Grid(); Children.Add(container);
        void Refresh()
        {
            container.Children.Clear(); var state = Enum.Parse<PlayerSettingsVisualState>((string)states.SelectedItem, true);
            var editor = new PlayerSettingsEditor(editableFields: state == PlayerSettingsVisualState.ReadOnly ? [] : SyncWatchPlayerSettings.Defaults.Keys, canSave: state != PlayerSettingsVisualState.ReadOnly, state: state);
            var view = new PlayerSettingsDialog(editor, (string)locales.SelectedItem, (string)sections.SelectedItem) { Persist = _ => fail.IsChecked != true, VerticalAlignment = VerticalAlignment.Center, HorizontalAlignment = HorizontalAlignment.Center };
            container.Children.Add(view);
        }
        void Theme() { Resources.MergedDictionaries.Clear(); Resources.MergedDictionaries.Add((ResourceDictionary)Application.Current.Resources.MergedDictionaries[0]["theme." + themes.SelectedItem]); SetResourceReference(BackgroundProperty, "theme.background.brush"); }
        sections.SelectionChanged += (_, _) => Refresh(); states.SelectionChanged += (_, _) => Refresh(); locales.SelectionChanged += (_, _) => Refresh(); themes.SelectionChanged += (_, _) => Theme(); Theme(); Refresh();
    }
}
