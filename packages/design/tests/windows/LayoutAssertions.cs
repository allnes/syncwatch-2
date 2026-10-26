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
            if (item.TryGetProperty("inkRegions", out var regions))
                foreach (var region in regions.EnumerateArray())
                {
                    int x = region.GetProperty("x").GetInt32(), y = region.GetProperty("y").GetInt32();
                    int w = region.GetProperty("width").GetInt32(), h = region.GetProperty("height").GetInt32();
                    var pixels = new byte[w * h * 4]; bitmap.CopyPixels(new Int32Rect(x, y, w, h), pixels, w * 4, 0);
                    bool found = Enumerable.Range(0, w * h).Any(i => pixels[i * 4] > pixels[i * 4 + 2] + 51);
                    Check(found == region.GetProperty("present").GetBoolean(), item.GetProperty("name").GetString() + ": paragraph ink in " + x + "," + y);
                }
            count++;
        }
        Check(count == 6, "shared axis/order/spacing/transparency/text alignment corpus");
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
        var nativeLeaf = new Border();
        var application = new ApplicationChrome(new Border(), nativeLeaf);
        DependencyObject? parent = null;
        foreach (bool presented in new[] { true, false, true, false, true })
        {
            application.PresentPlayer(presented); Layout(application, 800, 600);
            var current = VisualTreeHelper.GetParent(nativeLeaf);
            Check(current is not null && (parent is null || ReferenceEquals(parent, current)), "retained native parent identity");
            parent = current;
            var pane = Find<Grid>(application).Single(e => e.Children.Count == 1 && ReferenceEquals(e.Children[0],
                Find<Border>(application).Single(b => b.Child is Grid g && ReferenceEquals(g, current))));
            Check(pane.Visibility == (presented ? Visibility.Visible : Visibility.Hidden), "retained pane visibility");
            Check(pane.IsEnabled == presented && pane.IsHitTestVisible == presented, "hidden pane rejects input");
            Check(nativeLeaf.ActualWidth > 0 && nativeLeaf.ActualHeight > 0, "hidden pane keeps native geometry");
        }
        var libraryButton = new Button { Content = "Library" };
        var playerButton = new Button { Content = "Player" };
        var inputHost = new ApplicationChrome(libraryButton, playerButton);
        var inputWindow = new Window { Content = inputHost, SizeToContent = SizeToContent.WidthAndHeight, ShowInTaskbar = false };
        try
        {
            inputWindow.Show();
            foreach (bool presented in new[] { false, true, false, true, false })
            {
                inputHost.PresentPlayer(presented); Layout(inputHost, 800, 600);
                var target = inputHost.InputHitTest(new Point(inputHost.ActualWidth / 2, inputHost.ActualHeight / 2)) as DependencyObject;
                var expected = presented ? playerButton : libraryButton;
                bool reachedVisiblePane = false;
                for (var ancestor = target; ancestor is not null; ancestor = VisualTreeHelper.GetParent(ancestor))
                    if (ReferenceEquals(ancestor, expected)) { reachedVisiblePane = true; break; }
                Check(reachedVisiblePane, $"pointer input reaches the visible pane through the entire retained frame: presented={presented}, target={target?.GetType().Name}, visible={expected.IsVisible}");
            }
        }
        finally { inputWindow.Close(); }
        Console.WriteLine("Verified document-driven axis/order/spacing pixels and stable native input controls");
    }
}
