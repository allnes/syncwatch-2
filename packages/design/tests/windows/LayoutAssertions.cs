using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using SyncWatch.Design;

internal static class LayoutAssertions
{
    private static void Check(bool value, string name) { if (!value) throw new InvalidOperationException("Declarative layout: " + name); }
    private static IEnumerable<T> Find<T>(DependencyObject root) where T : DependencyObject
    {
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++) { var child = VisualTreeHelper.GetChild(root, i); if (child is T item) yield return item; foreach (var next in Find<T>(child)) yield return next; }
    }
    private static void Layout(FrameworkElement view, int width, int height) { view.Measure(new Size(width, height)); view.Arrange(new Rect(0, 0, width, height)); view.UpdateLayout(); }
    public static void Run()
    {
        using var data = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "layout-probes.json")));
        int count = 0;
        foreach (var item in data.RootElement.GetProperty("cases").EnumerateArray())
        {
            var node = JsonSerializer.Deserialize<DesignNode>(item.GetProperty("root").GetRawText(), new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
            var view = new DesignSurface(node); int width = item.GetProperty("width").GetInt32(), height = item.GetProperty("height").GetInt32(); Layout(view, width, height);
            var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32); bitmap.Render(view); var pixel = new byte[4];
            foreach (var probe in item.GetProperty("probes").EnumerateArray())
            {
                bitmap.CopyPixels(new Int32Rect(probe.GetProperty("x").GetInt32(), probe.GetProperty("y").GetInt32(), 1, 1), pixel, 4, 0);
                Check(probe.GetProperty("color").GetString() switch { "cyan" => pixel[0] > pixel[2] + 51, "yellow" => pixel[2] > pixel[0] + 51, _ => pixel[0] == 0 && pixel[1] == 0 && pixel[2] == 0 }, item.GetProperty("name").GetString() + " at " + probe.GetProperty("x") + "," + probe.GetProperty("y") + ": expected " + probe.GetProperty("color") + ", BGRA=" + string.Join(',', pixel));
            }
            count++;
        }
        Check(count == 4, "shared axis/order/spacing/transparency corpus");
        var editor = new SettingsEditor(editableFields: ["username"], canSave: true);
        var dialog = new SettingsDialog(editor, section: "connection"); Layout(dialog, 680, 420);
        var input = Find<TextBox>(dialog).Single(e => AutomationProperties.GetAutomationId(e) == "settings.field.username");
        input.Text = "ab"; input.CaretIndex = 1; dialog.SetLanguage("en");
        Check(ReferenceEquals(input, Find<TextBox>(dialog).Single(e => AutomationProperties.GetAutomationId(e) == "settings.field.username")) && input.CaretIndex == 1 && editor.Values["username"] == "ab", "observation refresh preserves control identity and caret");
        input.Text = "abc"; Check(editor.Values["username"] == "abc", "input remains attached after refresh");
        var library = new LibraryWorkspace(); library.Render(LibraryPresentation.Gallery(LibraryVisualState.Selected)); Layout(library, 800, 600);
        var query = Find<TextBox>(library).Single(e => AutomationProperties.GetAutomationId(e) == "library.search");
        query.Text = "Example"; query.CaretIndex = 2;
        Check(ReferenceEquals(query, Find<TextBox>(library).Single(e => AutomationProperties.GetAutomationId(e) == "library.search")), "filtering reconciles only changed list children");
        query.Text = "Example M"; Check(ReferenceEquals(query, Find<TextBox>(library).Single(e => AutomationProperties.GetAutomationId(e) == "library.search")), "continued typing remains attached");
        Console.WriteLine("Verified document-driven axis/order/spacing pixels and stable native input controls");
    }
}
