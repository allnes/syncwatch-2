using System.IO;
using System.Text.Json;
using System.Threading;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using SyncWatch.Design;

internal static class SelectionMenuAssertions
{
    private static void Check(bool value, string name) { if (!value) throw new InvalidOperationException("Selection menu: " + name); }
    private static IEnumerable<T> Find<T>(DependencyObject root) where T : DependencyObject
    {
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++) { var child = VisualTreeHelper.GetChild(root, i); if (child is T item) yield return item; foreach (var next in Find<T>(child)) yield return next; }
    }
    private static void Layout(FrameworkElement view, int width, int height) { view.Measure(new Size(width, height)); view.Arrange(new Rect(0, 0, width, height)); view.UpdateLayout(); }
    private static Button Entry(FrameworkElement view, string id) => Find<Button>(view).Single(b => AutomationProperties.GetAutomationId(b) == "selection." + id);
    private static void RejectWorkerMutation(Action operation, Func<bool> unchanged)
    {
        bool rejected = false;
        var worker = new Thread(() =>
        {
            try { operation(); }
            catch (InvalidOperationException) { rejected = true; }
        });
        worker.IsBackground = true;
        worker.Start();
        Check(worker.Join(TimeSpan.FromSeconds(5)) && rejected && unchanged(), "worker fails before publishing UI state");
    }
    public static void Run(Application application, ResourceDictionary dictionary)
    {
        using var corpus = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "selection-menu.json")));
        var options = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
        int cases = 0;
        foreach (var item in corpus.RootElement.GetProperty("cases").EnumerateArray())
        {
            var p = item.GetProperty("presentation").Deserialize<SelectionMenuPresentation>(options)!;
            Check(p.IsValid == item.GetProperty("valid").GetBoolean(), item.GetProperty("name").GetString()!);
            var received = new List<SelectionMenuRequest>(); string before = JsonSerializer.Serialize(p);
            foreach (var input in item.GetProperty("requests").EnumerateArray()) p.Dispatch(input.GetProperty("entryID").GetString()!, input.GetProperty("contextToken").GetString()!, received.Add);
            Check(received.SequenceEqual(item.GetProperty("expected").Deserialize<SelectionMenuRequest[]>(options)!), item.GetProperty("name").GetString()!);
            Check(before == JsonSerializer.Serialize(p), "requests do not change observations"); cases++;
        }
        Check(cases == 28, "shared request corpus");
        var ready = SelectionMenuFixtures.Presentation("playlist", "available");
        var mutableEntries = ready.Entries.ToList();
        var snapshotView = new SelectionMenu(); snapshotView.Render(ready with { Entries = mutableEntries });
        mutableEntries[1] = new("replaced", "Changed outside the observation");
        Check(snapshotView.Presentation.Entries[1] == ready.Entries[1], "accepted observation isolates caller-owned lists");
        var observed = snapshotView.Presentation;
        RejectWorkerMutation(() => snapshotView.Render(ready with { Revision = 99 }), () => ReferenceEquals(snapshotView.Presentation, observed));
        var primitive = new DesignSurface("SelectionMenu"); var context = primitive.Context;
        RejectWorkerMutation(() => primitive.Render(new() { Values = new() { ["kind"] = "audio" } }), () => ReferenceEquals(primitive.Context, context));
        var limit = ready with { Entries = Enumerable.Range(0, SyncWatchSelectionMenu.MaximumEntries).Select(i => new SelectionMenuEntry("item" + i, "Item")).ToArray() };
        Check(limit.IsValid && !(limit with { Entries = [.. limit.Entries, new("extra", "Overflow")] }).IsValid, "bounded entries");
        snapshotView.Render(limit with { Entries = [.. limit.Entries, new("extra", "Overflow"), new("extra2", "Overflow")] });
        Check(snapshotView.Presentation.Entries.Count == SyncWatchSelectionMenu.MaximumEntries + 1 && !snapshotView.Presentation.IsValid, "overflow snapshot remains bounded and invalid");
        int width = (int)SyncWatchTokens.LayoutSelectionGalleryWidth, height = (int)SyncWatchTokens.LayoutSelectionGalleryHeight;
        var view = new SelectionMenu(); var requests = new List<SelectionMenuRequest>(); view.SelectionRequested += requests.Add;
        view.Render(ready); Layout(view, width, height);
        Check(KeyboardNavigation.GetTabNavigation(Find<DesignSurface>(view).Single()) == KeyboardNavigationMode.Cycle, "declared component focus scope");
        Entry(view, "item1").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        Check(requests.Count == 1 && requests[0].Action == "selectMovie" && requests[0].Scope == "shared" && view.Presentation.SelectedID == "item0", "real control emits correlated request without acknowledgement");
        view.Render(ready with { SourceID = "next-source", Revision = 2 }, "ru"); Layout(view, width, height);
        Check(requests.Count == 1, "input-free observation update");
        Entry(view, "item1").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        Check(requests.Count == 2 && requests[1].SourceID == "next-source" && requests[1].Revision == 2, "control binding follows new source identity");
        view.Render(ready with { Enabled = false }); Layout(view, width, height); Entry(view, "item1").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        Check(requests.Count == 2 && !Entry(view, "item1").IsEnabled, "capability removed");
        const string literalLabel = "Literal {id} $kind ~play @type.bodySize";
        view.Render(ready with { Entries = [ready.Entries[0], new("item1", literalLabel)] }); Layout(view, width, height);
        Check(AutomationProperties.GetName(Entry(view, "item1")) == literalLabel && Find<TextBlock>(view).Any(t => t.Text == literalLabel), "labels do not become design expressions");
        foreach (string theme in new[] { "dark", "light" })
        {
            var selected = (ResourceDictionary)dictionary["theme." + theme]; application.Resources.MergedDictionaries.Add(selected);
            foreach (var kind in SyncWatchSelectionMenu.Kinds)
                foreach (string state in SyncWatchSelectionMenu.States)
                    foreach (string language in new[] { "en", "ru" })
                    {
                        var p = SelectionMenuFixtures.Presentation(kind.Id, state, language); var menu = new SelectionMenu(); int emitted = 0; menu.SelectionRequested += _ => emitted++;
                        menu.Render(p, language); Layout(menu, width, height);
                        var buttons = Find<Button>(menu).Where(b => AutomationProperties.GetAutomationId(b).StartsWith("selection.", StringComparison.Ordinal)).ToArray();
                        Check(buttons.Length == p.Entries.Count && buttons.All(b => b.ActualHeight == SyncWatchTokens.ControlMenuRowHeight), "shared row count and geometry");
                        Check(buttons.All(b => !string.IsNullOrWhiteSpace(AutomationProperties.GetName(b))), "full accessible labels");
                        Check(state != "readOnly" || buttons.All(b => !b.IsEnabled), "read-only menu");
                        var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32); bitmap.Render(menu); Check(emitted == 0, "render does not emit input");
                        var output = Environment.GetEnvironmentVariable("SYNCWATCH_DESIGN_SCREENSHOTS");
                        if (output is not null) { Directory.CreateDirectory(output); var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap)); using var stream = File.Create(Path.Combine(output, $"selection{kind.Id}{state}-{theme}-{language}-{width}x{height}.png")); encoder.Save(stream); }
                        if (state == "longList")
                        {
                            var scroll = Find<ScrollViewer>(menu).Single(); Check(scroll.ExtentHeight > scroll.ViewportHeight, "long lists scroll");
                            scroll.ScrollToBottom(); Layout(menu, width, height); Check(scroll.VerticalOffset > 0, "last entries reachable");
                        }
                    }
            application.Resources.MergedDictionaries.Remove(selected);
        }
        Console.WriteLine("Verified 28 selection scenarios, actual WPF events/scrolling and 48 native menu renders");
    }
}
