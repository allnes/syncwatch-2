using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.RegularExpressions;
using System.Windows.Controls;

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

public sealed class PlayerSubtitlePreview : DesignSurface
{
    public PlayerSettingsEditor Editor { get; }
    public PlayerSubtitlePreview(PlayerSettingsEditor editor, string language = "en") : base("subtitlePreview") { Editor = editor; Render(DesignBindings.Preview(editor.Values), language); }
}

public sealed class PlayerSettingsDialog : UserControl
{
    public PlayerSettingsEditor Editor { get; }
    public string UiLanguage { get; }
    public string Section { get; private set; }
    public Func<IReadOnlyDictionary<string, string>, bool> Persist { get; set; } = _ => false;
    public event Action? CloseRequested;
    public event Action? MoveRequested;
    public event Action<System.Windows.Vector>? MoveDeltaRequested;
    private System.Windows.Vector lastDrag;
    private readonly DesignSurface surface = new("PlayerSettings");
    public PlayerSettingsDialog(PlayerSettingsEditor? editor = null, string language = "en", string section = "playback")
    {
        Editor = editor ?? new(); UiLanguage = language; Section = SyncWatchPlayerSettings.Sections.Contains(section) ? section : "playback"; Content = surface; surface.ConfigureHost(this);
        surface.EventRequested += e =>
        {
            switch (e.Action)
            {
                case "selectSection": if (e.Value is string selected) SelectSection(selected); return;
                case "editField":
                    if (e.Payload is string id && e.Value is string value)
                    {
                        var field = SyncWatchPlayerSettings.Fields.SingleOrDefault(f => f.Id == id);
                        if (field?.Kind == "range" && double.TryParse(value, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var number)) value = PlayerSettingsEditor.Canonical(field.Minimum + Math.Round((number - field.Minimum) / field.Step) * field.Step);
                        Editor.Edit(id, value);
                    }
                    break;
                case "resetSection": Editor.Reset(Section); break;
                case "save": Editor.Save(values => Persist(values)); break;
                case "close": case "cancel": Editor.Cancel(); CloseRequested?.Invoke(); break;
                case "moveDialog":
                    if (e.Payload == "begin") { lastDrag = new(); MoveRequested?.Invoke(); }
                    else if (e.Value is string point) { var values = point.Split(',').Select(v => double.Parse(v, System.Globalization.CultureInfo.InvariantCulture)).ToArray(); if (values.Length == 2) { var current = new System.Windows.Vector(values[0], values[1]); MoveDeltaRequested?.Invoke(current - lastDrag); lastDrag = current; } }
                    else lastDrag = new();
                    break;
            }
            Refresh();
        }; Refresh();
    }
    public void SelectSection(string section) { if (SyncWatchPlayerSettings.Sections.Contains(section)) { Section = section; Refresh(); } }
    private void Refresh() => surface.Render(DesignBindings.PlayerSettings(Editor, Section, UiLanguage), UiLanguage);
}
