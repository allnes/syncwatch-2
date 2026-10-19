using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using SyncWatch.Design;

internal static class PlayerSettingsAssertions
{
    private static void Check(bool condition, string name) { if (!condition) throw new InvalidOperationException("Player settings assertion: " + name); }
    private static IEnumerable<T> Find<T>(DependencyObject root) where T : DependencyObject
    {
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++)
        {
            var child = VisualTreeHelper.GetChild(root, i);
            if (child is T value) yield return value;
            foreach (var nested in Find<T>(child)) yield return nested;
        }
    }
    private static T Element<T>(DependencyObject root, string id) where T : FrameworkElement => Find<T>(root).Single(e => AutomationProperties.GetAutomationId(e) == id);
    private static void Layout(FrameworkElement element, int width = 680, int height = 460)
    {
        element.Measure(new Size(width, height)); element.Arrange(new Rect(0, 0, width, height)); element.UpdateLayout();
    }
    private static RenderTargetBitmap Image(FrameworkElement element, int width, int height)
    {
        Layout(element, width, height); var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32); bitmap.Render(element); return bitmap;
    }
    public static void Run(Application application, ResourceDictionary dictionary)
    {
        using var corpus = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "player-settings.json")));
        var fixtures = corpus.RootElement.GetProperty("fields").EnumerateArray().ToArray();
        Check(fixtures.Select(f => f.GetProperty("id").GetString()!).ToHashSet().SetEquals(SyncWatchPlayerSettings.Defaults.Keys), "all fields have shared valid/invalid fixtures");
        foreach (var fixture in fixtures)
        {
            var descriptor = SyncWatchPlayerSettings.Fields.Single(f => f.Id == fixture.GetProperty("id").GetString());
            foreach (var value in fixture.GetProperty("valid").EnumerateArray()) Check(PlayerSettingsEditor.Valid(value.GetString()!, descriptor), descriptor.Id + " accepts " + value);
            foreach (var value in fixture.GetProperty("invalid").EnumerateArray()) Check(!PlayerSettingsEditor.Valid(value.GetString()!, descriptor), descriptor.Id + " rejects " + value);
        }
        var editor = new PlayerSettingsEditor(editableFields: SyncWatchPlayerSettings.Defaults.Keys, canSave: true);
        Check(editor.IsValid, "defaults"); editor.Edit("brightness", "0.35"); editor.Edit("subtitleSize", "36"); editor.Reset("image");
        Check(editor.Values["brightness"] == "0" && editor.Values["subtitleSize"] == "36", "reset affects only selected section"); editor.Edit("unknown", "ignored"); Check(!editor.Values.ContainsKey("unknown"), "unknown edit ignored");
        int writes = 0; editor.Edit("cursorDelay", "NaN"); Check(!editor.Save(_ => { writes++; return true; }) && writes == 0, "invalid draft cannot reach persistence"); editor.Cancel();
        editor.Edit("skipSeconds", "30"); Check(!editor.Save(_ => false) && editor.Message == "saveFailed" && editor.Values["skipSeconds"] == "30", "failed save retains draft without saved notice");
        IReadOnlyDictionary<string, string>? received = null;
        Check(editor.Save(v => { received = v; writes++; return true; }) && editor.State == PlayerSettingsVisualState.SavedNotice && editor.Message == "changesSaved", "acknowledged save");
        editor.Edit("skipSeconds", "60"); Check(received!["skipSeconds"] == "30", "save publishes an independent snapshot"); editor.Cancel(); Check(editor.Values["skipSeconds"] == "30", "cancel restores acknowledged baseline");
        var partial = new PlayerSettingsEditor(new Dictionary<string, string> { ["contrast"] = "0.5" }, ["brightness"], true); partial.Edit("brightness", "0.2"); partial.Edit("contrast", "0.4"); partial.Reset("image");
        Check(partial.Values["contrast"] == "0.5" && partial.Values["brightness"] == "0" && !partial.CanReset("audio") && !partial.CanReset("unknown"), "reset respects partial capabilities");
        var readOnly = new PlayerSettingsEditor(editableFields: SyncWatchPlayerSettings.Defaults.Keys); readOnly.Edit("brightness", "0.5"); readOnly.Reset("image");
        Check(readOnly.State == PlayerSettingsVisualState.ReadOnly && readOnly.Values["brightness"] == "0" && !readOnly.Save(_ => { writes++; return true; }) && writes == 1, "read-only rejects all writes");
        Check(!new PlayerSettingsEditor(editableFields: ["brightness"], canSave: true, state: PlayerSettingsVisualState.ReadOnly).Allows("brightness"), "explicit read-only state overrides supplied capabilities");
        Check(!new PlayerSettingsEditor(new Dictionary<string, string> { ["unknown"] = "value" }).IsValid && !new PlayerSettingsEditor(editableFields: ["unknown"], canSave: true).IsValid, "unknown data/capabilities invalid");
        var culture = CultureInfo.CurrentCulture;
        try { CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("de-DE"); Check(PlayerSettingsEditor.Canonical(0.35000000000001) == "0.35" && PlayerSettingsEditor.Canonical(-0.0) == "0" && PlayerSettingsEditor.Canonical(double.NaN) == "", "canonical numbers do not depend on system locale"); }
        finally { CultureInfo.CurrentCulture = culture; }
        Check(Enum.GetNames<PlayerSettingsVisualState>().Select(n => char.ToLowerInvariant(n[0]) + n[1..]).SequenceEqual(SyncWatchPlayerSettings.States), "state contract");
        var view = new PlayerSettingsDialog(editor); Layout(view);
        Element<ComboBox>(view, "playerSettings.field.skipSeconds").SelectedValue = "15";
        Element<CheckBox>(view, "playerSettings.field.timelinePreview").IsChecked = false;
        Check(editor.Values["skipSeconds"] == "15" && editor.Values["timelinePreview"] == "false", "real native controls edit draft");
        Element<Button>(view, "playerSettings.section.image").RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); Layout(view);
        Element<Slider>(view, "playerSettings.field.brightness").Value = 0.35; Check(editor.Values["brightness"] == "0.35", "native range serializes invariant step");
        Element<Button>(view, "playerSettings.resetSection").RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); Layout(view);
        Check(editor.Values["brightness"] == "0" && editor.Values["skipSeconds"] == "15", "native reset leaves other sections");
        view.SelectSection("subtitles"); Layout(view); Element<Button>(view, "playerSettings.color.cyan").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        Check(editor.Values["subtitleColor"] == "cyan" && Find<DesignSubtitle>(view).Count() == 1, "native swatch and preview");
        view.Persist = _ => false; Element<Button>(view, "playerSettings.save").RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); Check(editor.Message == "saveFailed", "native save failure");
        view.Persist = _ => true; Element<Button>(view, "playerSettings.save").RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); Check(editor.State == PlayerSettingsVisualState.SavedNotice, "native acknowledged save");
        Check(KeyboardNavigation.GetTabNavigation(view) == KeyboardNavigationMode.Cycle && Element<Button>(view, "playerSettings.save").IsDefault && Element<Button>(view, "playerSettings.cancel").IsCancel, "native dialog keyboard contract");
        bool closed = false; view.CloseRequested += () => closed = true; editor.Edit("subtitleColor", "warm"); Element<Button>(view, "playerSettings.cancel").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        Check(closed && editor.Values["subtitleColor"] == "cyan", "cancel restores saved baseline and closes");
        var locked = new PlayerSettingsDialog(readOnly); Layout(locked);
        Check(!Element<Button>(locked, "playerSettings.save").IsEnabled && !Element<Button>(locked, "playerSettings.resetSection").IsEnabled && !Element<ComboBox>(locked, "playerSettings.field.skipSeconds").IsEnabled, "read-only native fields and save/reset disabled");
        Preview();
        string? output = Environment.GetEnvironmentVariable("SYNCWATCH_DESIGN_SCREENSHOTS"); if (output is not null) Directory.CreateDirectory(output);
        int images = 0;
        foreach (var theme in new[] { "dark", "light" })
        {
            application.Resources.MergedDictionaries.Add((ResourceDictionary)dictionary["theme." + theme]);
            foreach (var section in SyncWatchPlayerSettings.Sections)
                foreach (var state in Enum.GetValues<PlayerSettingsVisualState>())
                    foreach (var language in new[] { "en", "ru" })
                    {
                        var fixture = new PlayerSettingsEditor(editableFields: SyncWatchPlayerSettings.Defaults.Keys, canSave: state != PlayerSettingsVisualState.ReadOnly, state: state);
                        var dialog = new PlayerSettingsDialog(fixture, language, section); var bitmap = Image(dialog, 680, 460);
                        foreach (var choice in Find<ComboBox>(dialog)) if (choice.SelectedItem is KeyValuePair<string, string> selected) Check(Element<TextBlock>(choice, "settings.choiceLabel").Text == selected.Value, "native human-readable choice labels");
                        if (state == PlayerSettingsVisualState.SavedNotice) Check(Element<TextBlock>(dialog, "playerSettings.status").Text == SyncWatchCopy.Text("changesSaved", language), "saved fixture status");
                        if (output is not null) { var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(bitmap)); using var file = File.Create(Path.Combine(output, $"playersettings{section}{state}-{theme}-{language}-680x460.png")); png.Save(file); }
                        images++;
                    }
            application.Resources.MergedDictionaries.Remove((ResourceDictionary)dictionary["theme." + theme]);
        }
        Console.WriteLine($"Verified player settings corpus for {fixtures.Length} fields, native draft/save/reset/cancel/capabilities, actual subtitle glyphs and {images} renders");
    }
    private static void Preview()
    {
        (int Count, double Y, double Red, double Blue) Pixels(Dictionary<string, string> changes)
        {
            var preview = new PlayerSubtitlePreview(new PlayerSettingsEditor(changes)); var bitmap = Image(preview, 440, 130);
            byte[] pixels = new byte[440 * 130 * 4]; bitmap.CopyPixels(pixels, 440 * 4, 0);
            int count = 0; double ySum = 0, red = 0, blue = 0;
            for (int y = 0; y < 130; y++) for (int x = 0; x < 440; x++) { int i = (y * 440 + x) * 4; if (Math.Max(pixels[i], Math.Max(pixels[i + 1], pixels[i + 2])) > 76) { count++; ySum += y / 130.0; red += pixels[i + 2] / 255.0; blue += pixels[i] / 255.0; } }
            Check(count > 100, "preview contains actual glyph pixels"); return (count, ySum / count, red / count, blue / count);
        }
        var bottom = Pixels([]); var top = Pixels(new() { ["subtitlePosition"] = "top" }); Check(bottom.Y > top.Y + .2, "preview responds to position");
        Check(Pixels(new() { ["subtitleSize"] = "48" }).Count > bottom.Count, "preview responds to font size"); var cyan = Pixels(new() { ["subtitleColor"] = "cyan" }); Check(cyan.Blue > cyan.Red + .1, "preview responds to swatch");
        Check(Pixels(new() { ["subtitleSize"] = "NaN", ["subtitlePadding"] = "Infinity", ["subtitleOffset"] = "1e9", ["subtitleColor"] = "black", ["outlineColor"] = "white", ["subtitleFont"] = "unknown", ["subtitlePosition"] = "unknown" }).Count == bottom.Count, "invalid values render safe defaults");
    }
}
