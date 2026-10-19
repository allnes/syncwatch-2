using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using SyncWatch.Design;

internal static class CallAssertions
{
    private static void Check(bool value, string name) { if (!value) throw new InvalidOperationException("Call assertion: " + name); }
    private static IEnumerable<T> Find<T>(DependencyObject root) where T : DependencyObject
    {
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++) { var child = VisualTreeHelper.GetChild(root, i); if (child is T item) yield return item; foreach (var next in Find<T>(child)) yield return next; }
    }
    private static T Element<T>(DependencyObject root, string id) where T : FrameworkElement => Find<T>(root).Single(e => AutomationProperties.GetAutomationId(e) == id);
    private static bool? Bool(JsonElement fixture, string key) => fixture.GetProperty(key).ValueKind == JsonValueKind.Null ? null : fixture.GetProperty(key).GetBoolean();
    private static CallRequest Request(JsonElement value) => new(value.GetProperty("action").GetString()!, value.GetProperty("values").EnumerateArray().Select(v => v.GetDouble()).ToArray());
    private static void Layout(FrameworkElement view, int width = 300, int height = 210) { view.Measure(new Size(width, height)); view.Arrange(new Rect(0, 0, width, height)); view.UpdateLayout(); }
    public static void Run(Application application, ResourceDictionary dictionary)
    {
        using var corpus = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "call-actions.json")));
        int scenarios = 0;
        foreach (var item in corpus.RootElement.GetProperty("cases").EnumerateArray())
        {
            var p = new CallPresentation { State = Enum.Parse<CallVisualState>(item.GetProperty("state").GetString()!, true), Preview = Enum.Parse<CallPreviewState>(item.GetProperty("preview").GetString()!, true), Joined = Bool(item, "joined"), MicrophoneEnabled = Bool(item, "microphoneEnabled"), CameraEnabled = Bool(item, "cameraEnabled"), Volume = item.GetProperty("volume").ValueKind == JsonValueKind.Null ? null : item.GetProperty("volume").GetDouble(), EnabledActions = item.GetProperty("enabledActions").EnumerateArray().Select(a => a.GetString()!).ToHashSet() };
            var received = new List<CallRequest>();
            foreach (var input in item.GetProperty("requests").EnumerateArray()) p.Dispatch(Request(input), received.Add);
            var expected = item.GetProperty("expected").EnumerateArray().Select(Request).ToArray();
            Check(received.Count == expected.Length && received.Zip(expected).All(pair => pair.First.Action == pair.Second.Action && pair.First.Values.SequenceEqual(pair.Second.Values)), item.GetProperty("name").GetString()!);
            Check(p.Joined == Bool(item, "joined") && p.State == Enum.Parse<CallVisualState>(item.GetProperty("state").GetString()!, true), "no self acknowledgement");
            Check(p.ShowsRemoteSurface == item.GetProperty("showsRemote").GetBoolean() && p.ShowsLocalPreview == item.GetProperty("showsLocal").GetBoolean(), "slot visibility");
            Check(p.PreviewLabel(false) != "cameraActive" && p.DisplayedVolume is >= 0 and <= 1, "safe fallback display"); scenarios++;
        }
        Check(scenarios == 45, "shared corpus");
        var ready = CallPresentation.Gallery(SyncWatchCall.GalleryCases[2]); int invalid = 0;
        foreach (double value in new[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity })
        {
            foreach (var input in new[] { new CallRequest("move", value, 0), new CallRequest("resize", 300, value), new CallRequest("setCallVolume", value), new CallRequest("setCameraEnabled", value) }) ready.Dispatch(input, _ => invalid++);
            Check(!(ready with { Volume = value }).Allows("setCallVolume") && (ready with { Volume = value }).DisplayedVolume == 0, "nonfinite observation");
        }
        Check(invalid == 0, "nonfinite input");
        Check(Enum.GetValues<CallVisualState>().Select(CallPresentation.Key).SequenceEqual(SyncWatchCall.States), "call states");
        Check(Enum.GetValues<CallPreviewState>().Select(CallPresentation.Key).SequenceEqual(SyncWatchCall.PreviewStates), "preview states");
        var shell = new CallWindowShell(); var requests = new List<CallRequest>(); shell.ActionRequested += requests.Add;
        var remote = new Border { Background = Brushes.Green }; var local = new Border { Background = Brushes.Blue };
        shell.RemoteSurface = remote; shell.LocalPreview = local; shell.Render(ready); Layout(shell); shell.Render(ready with { Volume = 0.4 }, "ru"); Layout(shell);
        Check(requests.Count == 0 && VisualTreeHelper.GetParent(remote) is Grid && VisualTreeHelper.GetParent(local) is Grid, "input-free observation and single-parent reattachment");
        Element<Button>(shell, "call.setMicrophoneEnabled").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        Element<Slider>(shell, "call.setCallVolume").Value = 0.3;
        Element<Thumb>(shell, "call.move").RaiseEvent(new DragDeltaEventArgs(12, -4));
        Element<Thumb>(shell, "call.resize").RaiseEvent(new DragDeltaEventArgs(-1000, -1000));
        Check(requests.Count == 4 && requests[0].Action == "setMicrophoneEnabled" && requests[0].Values.SequenceEqual(new[] { 0.0 }), "real controls emit bounded requests");
        Check(requests[3].Values.SequenceEqual(new[] { SyncWatchTokens.LayoutCallMinimumWidth, SyncWatchTokens.LayoutCallMinimumHeight }), "resize clamps to shared minimum");
        Check(shell.Presentation.MicrophoneEnabled == true && shell.Presentation.Volume == 0.4, "UI requests cannot mutate observations");
        shell.Render(ready with { Joined = false }); Layout(shell);
        Check(!Element<Button>(shell, "call.setMicrophoneEnabled").IsEnabled && !Element<Slider>(shell, "call.setCallVolume").IsEnabled && VisualTreeHelper.GetParent(local) is null, "not joined gates media/self-view");
        shell.Render(ready with { State = CallVisualState.Closed }); Layout(shell); Check(VisualTreeHelper.GetParent(remote) is null && VisualTreeHelper.GetParent(local) is null, "closed detaches both slots without claiming provider teardown");
        shell.LocalPreview = remote;
        try { shell.Render(ready); throw new InvalidOperationException("Expected alias rejection"); } catch (ArgumentException) { }
        foreach (string theme in new[] { "dark", "light" })
        {
            var selected = (ResourceDictionary)dictionary["theme." + theme]; application.Resources.MergedDictionaries.Add(selected);
            foreach (var item in SyncWatchCall.GalleryCases)
                foreach (string language in new[] { "en", "ru" })
                    foreach (var (width, height) in new[] { (300, 210), (420, 300) })
                    {
                        var p = CallPresentation.Gallery(item); var view = new CallWindowShell { RemoteSurface = new Border { Background = Brushes.Green }, LocalPreview = new Border { Background = Brushes.Blue } }; view.Render(p, language); Layout(view, width, height);
                        foreach (var button in Find<Button>(view))
                        {
                            var point = button.TransformToAncestor(view).Transform(new Point());
                            Check(button.ActualWidth >= SyncWatchTokens.LayoutCallWindowButtonSize && point.X >= 0 && point.Y >= 0 && point.X + button.ActualWidth <= width && point.Y + button.ActualHeight <= height, "buttons fit compact viewport");
                            Check(!string.IsNullOrWhiteSpace(AutomationProperties.GetName(button)), "localized button accessibility");
                        }
                        var grip = Element<Thumb>(view, "call.resize"); var gripOrigin = grip.TransformToAncestor(view).Transform(new Point());
                        Check(grip.Focusable && gripOrigin.X > width / 2 && gripOrigin.Y > height / 2 && gripOrigin.X + grip.ActualWidth <= width && gripOrigin.Y + grip.ActualHeight <= height, "keyboard-capable resize grip stays inside the bottom-right quadrant");
                        var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32); bitmap.Render(view); byte[] pixel = new byte[4];
                        bitmap.CopyPixels(new Int32Rect(width - 20, 110, 1, 1), pixel, 4, 0); Check(p.ShowsRemoteSurface ? pixel[1] > 100 : pixel[1] == 0, "remote surface gated independently of membership");
                        bitmap.CopyPixels(new Int32Rect(16, 48, 1, 1), pixel, 4, 0); Check(p.ShowsLocalPreview ? pixel[0] > pixel[2] + 80 : pixel[0] < pixel[2] + 80, "true self-view slot gating");
                        var output = Environment.GetEnvironmentVariable("SYNCWATCH_DESIGN_SCREENSHOTS"); if (output is not null) { Directory.CreateDirectory(output); var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap)); using var stream = File.Create(Path.Combine(output, $"call{item.Id}-{theme}-{language}-{width}x{height}.png")); encoder.Save(stream); }
                    }
            application.Resources.MergedDictionaries.Remove(selected);
        }
        Console.WriteLine("Verified 45 call request/observation scenarios, real WPF controls, owned slots and 80 call renders");
    }
}
