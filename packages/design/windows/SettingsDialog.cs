using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace SyncWatch.Design;

public enum SettingsVisualState { Editing, SavedNotice, InvalidConfiguration }

public sealed class SettingsEditor
{
    private Dictionary<string, string> values;
    private Dictionary<string, string> original;
    public IReadOnlyDictionary<string, string> Values => new ReadOnlyDictionary<string, string>(new Dictionary<string, string>(values));
    public IReadOnlySet<string> EditableFields { get; }
    public bool CanSave { get; }
    public SettingsVisualState State { get; private set; }
    public string Message { get; private set; } = "";

    public SettingsEditor(IReadOnlyDictionary<string, string>? initial = null, IEnumerable<string>? editableFields = null,
        bool canSave = false, SettingsVisualState state = SettingsVisualState.Editing)
    {
        values = new(SyncWatchSettings.Defaults);
        foreach (var pair in initial ?? new Dictionary<string, string>()) values[pair.Key] = pair.Value;
        original = new(values); EditableFields = new HashSet<string>(editableFields ?? []); CanSave = canSave; State = state;
        if (state == SettingsVisualState.InvalidConfiguration) Message = "invalidConfiguration";
    }

    public void Edit(string id, string value)
    {
        if (!EditableFields.Contains(id) || !SyncWatchSettings.Fields.Any(f => f.Id == id)) return;
        values[id] = value; State = SettingsVisualState.Editing; Message = "";
    }

    public bool IsValid => values.Keys.ToHashSet().SetEquals(SyncWatchSettings.Defaults.Keys)
        && EditableFields.All(SyncWatchSettings.Defaults.ContainsKey) && SyncWatchSettings.Fields.All(field =>
            values.TryGetValue(field.Id, out var value) && value.Length <= field.MaxLength && !value.Any(c => c < 32)
            && (field.Kind != "choice" || field.Options.Contains(value)) && (field.Kind != "boolean" || value is "true" or "false"));

    public bool Save(Func<IReadOnlyDictionary<string, string>, bool> persist)
    {
        if (!CanSave) return false;
        if (!IsValid) { State = SettingsVisualState.InvalidConfiguration; Message = "invalidConfiguration"; return false; }
        if (!persist(Values)) { State = SettingsVisualState.InvalidConfiguration; Message = "saveFailed"; return false; }
        original = new(values); State = SettingsVisualState.SavedNotice; Message = "changesSaved"; return true;
    }

    public void Cancel() { values = new(original); State = SettingsVisualState.Editing; Message = ""; }
}

public sealed class SettingsDialog : UserControl
{
    public SettingsEditor Editor { get; }
    public string UiLanguage { get; private set; }
    public string Section { get; private set; }
    public Func<IReadOnlyDictionary<string, string>, bool> Persist { get; set; } = _ => false;
    public event Action? CloseRequested;
    public event Action? MoveRequested;
    private readonly Grid root = new();
    private TextBlock status = new();
    private readonly List<FrameworkElement> tabButtons = [];

    public SettingsDialog(SettingsEditor? editor = null, string language = "en", string section = "interface")
    {
        Editor = editor ?? new(); UiLanguage = language;
        Section = SyncWatchSettings.Sections.Contains(section) ? section : "interface";
        Width = SyncWatchTokens.LayoutSettingsWidth; Height = SyncWatchTokens.LayoutSettingsHeight;
        FontSize = SyncWatchTokens.TypeSettingsBodySize;
        Clip = new RectangleGeometry(new Rect(0, 0, Width, Height), SyncWatchTokens.ControlCompactDialogRadius, SyncWatchTokens.ControlCompactDialogRadius);
        SetResourceReference(ForegroundProperty, "theme.text.brush");
        var border = new Border { Child = root, CornerRadius = SyncWatchTokens.ControlCompactDialogRadiusCornerRadius, BorderThickness = SyncWatchTokens.ControlBorderWidthThickness };
        border.SetResourceReference(Border.BackgroundProperty, "theme.surface.brush"); border.SetResourceReference(Border.BorderBrushProperty, "theme.border.brush");
        Content = border;
        KeyboardNavigation.SetTabNavigation(this, KeyboardNavigationMode.Cycle);
        Render();
    }

    public void SetLanguage(string language) { UiLanguage = language; Render(); }
    public void SelectSection(string section) { if (SyncWatchSettings.Sections.Contains(section)) { Section = section; Render(); } }
    private string T(string id) => id.Length == 0 ? "" : SyncWatchCopy.Text(id, UiLanguage);
    private TextBlock Text(string value, bool muted = false) { var t = new TextBlock { Text = value, TextWrapping = TextWrapping.Wrap }; t.SetResourceReference(TextBlock.ForegroundProperty, muted ? "theme.textSecondary.brush" : "theme.text.brush"); return t; }
    private Button Button(string id, Action clicked, bool filled = false)
    {
        var button = new Button { Content = T(id), Margin = new Thickness(SyncWatchTokens.ControlCompactGap, 0, 0, 0) };
        button.SetResourceReference(StyleProperty, filled ? "SyncWatch.SettingsFilledButton" : "SyncWatch.SettingsButton");
        AutomationProperties.SetAutomationId(button, "settings." + id); button.Click += (_, _) => clicked(); return button;
    }
    private Border Line() { var b = new Border { Height = SyncWatchTokens.ControlBorderWidth, Width = double.NaN }; b.SetResourceReference(Border.BackgroundProperty, "theme.border.brush"); return b; }
    private void Close() { Editor.Cancel(); CloseRequested?.Invoke(); }
    private void Render()
    {
        root.Children.Clear(); root.RowDefinitions.Clear(); tabButtons.Clear();
        foreach (var height in new[] { SyncWatchTokens.LayoutSettingsHeaderHeight, 1, -1, 1, SyncWatchTokens.LayoutSettingsFooterHeight })
            root.RowDefinitions.Add(new RowDefinition { Height = height < 0 ? new GridLength(1, GridUnitType.Star) : new GridLength(height) });
        var header = new DockPanel { Margin = new Thickness(SyncWatchTokens.LayoutSettingsCardPadding, 0, SyncWatchTokens.LayoutSettingsCardPadding, 0) };
        var close = Button("close", Close); close.TabIndex = 0; DockPanel.SetDock(close, Dock.Right); header.Children.Add(close);
        var title = Text(T("brand") + " · " + T("openSettings")); title.FontWeight = FontWeights.Bold; title.FontSize = SyncWatchTokens.TypeSettingsTitleSize; title.VerticalAlignment = VerticalAlignment.Center; title.MouseLeftButtonDown += (_, _) => MoveRequested?.Invoke(); header.Children.Add(title); root.Children.Add(header);
        var topLine = Line(); Grid.SetRow(topLine, 1); root.Children.Add(topLine);
        var body = new Grid(); body.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(SyncWatchTokens.LayoutSettingsSidebarWidth) }); body.ColumnDefinitions.Add(new ColumnDefinition()); Grid.SetRow(body, 2); root.Children.Add(body);
        var sidebar = new StackPanel { Margin = SyncWatchTokens.LayoutSettingsCardPaddingThickness };
        foreach (var id in SyncWatchSettings.Sections)
        {
            var button = new Button { Content = Text(T(id)), MinHeight = SyncWatchTokens.LayoutSettingsSidebarRowHeight, HorizontalContentAlignment = HorizontalAlignment.Stretch };
            button.SetResourceReference(StyleProperty, "SyncWatch.SettingsTab");
            if (id == Section) button.SetResourceReference(BackgroundProperty, "theme.selection.brush");
            AutomationProperties.SetAutomationId(button, "settings.section." + id); button.Click += (_, _) => SelectSection(id);
            button.TabIndex = 1 + tabButtons.Count; sidebar.Children.Add(button); tabButtons.Add(button);
        }
        var rail = new Border { Child = sidebar }; rail.SetResourceReference(Border.BackgroundProperty, "theme.backgroundDeep.brush"); body.Children.Add(rail);
        var form = new StackPanel { Margin = SyncWatchTokens.LayoutSettingsContentPaddingThickness };
        var heading = Text(T(Section)); heading.FontSize = SyncWatchTokens.TypeSettingsSectionSize; heading.FontWeight = FontWeights.Bold; form.Children.Add(heading);
        var hint = Text(T(Section + "Hint"), true); hint.Margin = new Thickness(0, SyncWatchTokens.ControlBorderWidth, 0, SyncWatchTokens.ControlCompactGap); form.Children.Add(hint);
        foreach (var field in SyncWatchSettings.Fields.Where(f => f.Section == Section)) form.Children.Add(Field(field));
        if (!SyncWatchSettings.Fields.Any(f => f.Section == Section && Editor.EditableFields.Contains(f.Id))) form.Children.Add(Text(T("settingsUnavailable"), true));
        var scroll = new ScrollViewer { Content = form, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };
        Grid.SetColumn(scroll, 1); body.Children.Add(scroll);
        var bottomLine = Line(); Grid.SetRow(bottomLine, 3); root.Children.Add(bottomLine);
        var footer = new DockPanel { Margin = SyncWatchTokens.LayoutSettingsCardPaddingThickness };
        var save = Button("save", () => { Editor.Save(Persist); UpdateStatus(); }, true); save.TabIndex = 101; save.IsEnabled = Editor.CanSave; save.IsDefault = true; DockPanel.SetDock(save, Dock.Right); footer.Children.Add(save);
        var cancel = Button("cancel", Close); cancel.TabIndex = 100; cancel.IsCancel = true; DockPanel.SetDock(cancel, Dock.Right); footer.Children.Add(cancel);
        status = Text(""); status.FontSize = SyncWatchTokens.TypeCaptionSize; status.VerticalAlignment = VerticalAlignment.Center; AutomationProperties.SetAutomationId(status, "settings.status"); footer.Children.Add(status); Grid.SetRow(footer, 4); root.Children.Add(footer); UpdateStatus();
    }
    private void UpdateStatus()
    {
        status.Text = T(!Editor.CanSave ? "settingsReadOnly" : Editor.State == SettingsVisualState.SavedNotice ? "changesSaved" : Editor.Message);
        status.SetResourceReference(TextBlock.ForegroundProperty, Editor.State == SettingsVisualState.SavedNotice ? "theme.success.brush" : "theme.textSecondary.brush");
    }
    private FrameworkElement Field(SyncWatchSettingsField field)
    {
        var stack = new StackPanel { Margin = new Thickness(0, 0, 0, SyncWatchTokens.ControlCompactGap), Width = field.Section == "interface" ? SyncWatchTokens.LayoutSettingsInterfaceFieldWidth : SyncWatchTokens.LayoutSettingsFieldWidth, HorizontalAlignment = HorizontalAlignment.Left };
        var enabled = Editor.EditableFields.Contains(field.Id); FrameworkElement input;
        if (field.Kind == "boolean")
        {
            var toggle = new CheckBox { Content = T(field.Label), IsChecked = Editor.Values[field.Id] == "true", MinHeight = SyncWatchTokens.LayoutSettingsControlHeight };
            toggle.SetResourceReference(ForegroundProperty, "theme.text.brush");
            toggle.SetResourceReference(StyleProperty, "SyncWatch.SettingsToggle");
            toggle.Checked += (_, _) => { Editor.Edit(field.Id, "true"); UpdateStatus(); }; toggle.Unchecked += (_, _) => { Editor.Edit(field.Id, "false"); UpdateStatus(); }; input = toggle;
        }
        else
        {
            stack.Children.Add(Text(T(field.Label), true));
            if (field.Kind == "choice")
            {
                var choice = new ComboBox { ItemsSource = field.Options.Select(o => new KeyValuePair<string, string>(o, T("option" + char.ToUpperInvariant(o[0]) + o[1..]))).ToArray(), DisplayMemberPath = "Value", SelectedValuePath = "Key", SelectedValue = Editor.Values[field.Id], MinHeight = SyncWatchTokens.LayoutSettingsControlHeight };
                choice.SetResourceReference(StyleProperty, "SyncWatch.SettingsChoice");
                choice.SelectionChanged += (_, _) => { if (choice.SelectedValue is string value) { Editor.Edit(field.Id, value); UpdateStatus(); } }; input = choice;
            }
            else
            {
                var box = new TextBox { Text = Editor.Values[field.Id], MinHeight = SyncWatchTokens.LayoutSettingsControlHeight, Height = SyncWatchTokens.LayoutSettingsControlHeight };
                box.SetResourceReference(StyleProperty, "SyncWatch.SettingsField"); box.TextChanged += (_, _) => { Editor.Edit(field.Id, box.Text); UpdateStatus(); }; input = box;
            }
        }
        if (input is Control control) control.TabIndex = 10 + Array.FindIndex(SyncWatchSettings.Fields, f => f.Id == field.Id);
        input.IsEnabled = enabled; AutomationProperties.SetAutomationId(input, "settings.field." + field.Id); AutomationProperties.SetName(input, T(field.Label)); stack.Children.Add(input); return stack;
    }
}

public sealed class SettingsGallery : DockPanel
{
    public SettingsGallery()
    {
        var toolbar = new StackPanel { Orientation = Orientation.Horizontal, Margin = SyncWatchTokens.LayoutPanelPaddingThickness };
        var sections = new ComboBox { ItemsSource = SyncWatchSettings.Sections, SelectedIndex = 0 };
        var states = new ComboBox { ItemsSource = SyncWatchSettings.States, SelectedIndex = 0 };
        var languages = new ComboBox { ItemsSource = new[] { "en", "ru" }, SelectedIndex = 0 };
        var themes = new ComboBox { ItemsSource = new[] { "dark", "light" }, SelectedIndex = 0 };
        var fail = new CheckBox { Content = "Fail save" };
        foreach (var item in new UIElement[] { sections, states, languages, themes, fail }) toolbar.Children.Add(item);
        DockPanel.SetDock(toolbar, Dock.Top); Children.Add(toolbar);
        var container = new Grid(); Children.Add(container);
        void Refresh()
        {
            container.Children.Clear();
            var editor = new SettingsEditor(editableFields: SyncWatchSettings.Defaults.Keys, canSave: true, state: Enum.Parse<SettingsVisualState>((string)states.SelectedItem, true));
            var view = new SettingsDialog(editor, (string)languages.SelectedItem, (string)sections.SelectedItem) { HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, Persist = _ => fail.IsChecked != true };
            container.Children.Add(view);
        }
        void Theme()
        {
            Resources.MergedDictionaries.Clear();
            Resources.MergedDictionaries.Add((ResourceDictionary)Application.Current.Resources.MergedDictionaries[0]["theme." + themes.SelectedItem]);
            SetResourceReference(BackgroundProperty, "theme.background.brush");
        }
        sections.SelectionChanged += (_, _) => Refresh(); states.SelectionChanged += (_, _) => Refresh(); languages.SelectionChanged += (_, _) => Refresh(); themes.SelectionChanged += (_, _) => Theme();
        Theme(); Refresh();
    }
}
