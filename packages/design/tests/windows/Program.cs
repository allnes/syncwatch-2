using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using SyncWatch.Design;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "design-manifest.json")));
        var manifest = document.RootElement;
        var application = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
        var dictionary = new ResourceDictionary { Source = new Uri("SyncWatchTheme.g.xaml", UriKind.Relative) };
        var count = 0;
        foreach (var token in manifest.GetProperty("tokens").EnumerateArray())
        {
            var id = token.GetProperty("id").GetString()!;
            var name = string.Concat(id.Split('.').Select(part => char.ToUpperInvariant(part[0]) + part[1..]));
            var value = token.GetProperty("value");
            if (token.GetProperty("type").GetString() == "color")
            {
                var hex = value.GetString()!;
                var bytes = Convert.FromHexString(hex[1..]);
                var expected = Color.FromArgb(bytes[3], bytes[0], bytes[1], bytes[2]);
                Check((Color)dictionary[id] == expected, id);
                Check(((SolidColorBrush)dictionary[id + ".brush"]).Color == expected, id + ".brush");
                Check((Color)typeof(SyncWatchTokens).GetProperty(name)!.GetValue(null)! == expected, name);
                count += 3;
            }
            else
            {
                var expected = value.GetDouble();
                Check((double)dictionary[id] == expected, id);
                Check((Thickness)dictionary[id + ".thickness"] == new Thickness(expected), id + ".thickness");
                Check((CornerRadius)dictionary[id + ".cornerRadius"] == new CornerRadius(expected), id + ".cornerRadius");
                Check((double)typeof(SyncWatchTokens).GetField(name)!.GetValue(null)! == expected, name);
                Check((Thickness)typeof(SyncWatchTokens).GetProperty(name + "Thickness")!.GetValue(null)! == new Thickness(expected), name);
                Check((CornerRadius)typeof(SyncWatchTokens).GetProperty(name + "CornerRadius")!.GetValue(null)! == new CornerRadius(expected), name);
                count += 6;
            }
        }

        // DynamicResource must update an existing element when the selected theme changes.
        application.Resources.MergedDictionaries.Add(dictionary);
        var panel = new Border();
        panel.SetResourceReference(Border.BackgroundProperty, "theme.background.brush");
        var window = new Window { Content = panel, Width = 200, Height = 100, ShowInTaskbar = false };
        panel.Measure(new Size(200, 100));
        panel.Arrange(new Rect(0, 0, 200, 100));
        ResourceDictionary? previous = null;
        foreach (var theme in manifest.GetProperty("themes").EnumerateObject())
        {
            if (previous is not null)
            {
                application.Resources.MergedDictionaries.Remove(previous);
            }

            previous = (ResourceDictionary)dictionary["theme." + theme.Name];
            application.Resources.MergedDictionaries.Add(previous);
            foreach (var role in theme.Value.EnumerateObject())
            {
                var id = role.Value.GetString()!;
                Check(((SolidColorBrush)previous["theme." + role.Name + ".brush"]).Color == (Color)dictionary[id], role.Name);
                count++;
            }

            application.Dispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
            Check(panel.Background is SolidColorBrush brush && brush.Color == (Color)dictionary[theme.Value.GetProperty("background").GetString()!], "DynamicResource theme change");
            count++;
        }

        window.Close();
        application.Resources.MergedDictionaries.Add(new ResourceDictionary { Source = new Uri("SyncWatchComponents.xaml", UriKind.Relative) });
        VerifyLibrary(application, dictionary);
        SettingsAssertions.Run(application, dictionary);
        PlayerAssertions.Run(application, dictionary);
        PlayerSettingsAssertions.Run(application, dictionary);
        LayoutAssertions.Run();
        CallAssertions.Run(application, dictionary);
        application.Shutdown();
        Console.WriteLine(string.Create(CultureInfo.InvariantCulture, $"Verified {count} compiled C#/WPF resources and theme assertions"));
    }

    private static IEnumerable<T> Descendants<T>(DependencyObject parent) where T : DependencyObject
    {
        for (int index = 0; index < VisualTreeHelper.GetChildrenCount(parent); index++)
        {
            var child = VisualTreeHelper.GetChild(parent, index);
            if (child is T typed) yield return typed;
            foreach (var descendant in Descendants<T>(child)) yield return descendant;
        }
    }

    private static void VerifyLibrary(Application application, ResourceDictionary dictionary)
    {
        var events = new List<string>();
        void Receive(string action, string? value) => events.Add(action + ":" + value);
        new LibraryPresentation().Dispatch("chooseFolder", null, Receive);
        foreach (var state in Enum.GetValues<LibraryVisualState>())
        {
            var presentation = LibraryPresentation.Gallery(state);
            presentation.Dispatch("openCall", null, Receive);
            presentation.Dispatch("selectMovie", "removed-id", Receive);
            presentation.Dispatch("startWatching", null, Receive);
        }
        Check(events.SequenceEqual(new[] { "startWatching:" }), "capabilities and missing media");
        LibraryPresentation.Gallery(LibraryVisualState.Scanning).Dispatch("search", "film", Receive);
        var selected = LibraryPresentation.Gallery(LibraryVisualState.Selected);
        selected.Dispatch("selectMovie", "1", Receive);
        (selected with { SelectedId = "removed-id" }).Dispatch("startWatching", null, Receive);
        Check(events.SequenceEqual(new[] { "startWatching:", "selectMovie:1" }), "stale selection");
        Check(SyncWatchCopy.Text("library", "ru") == "Библиотека фильмов", "Russian copy");
        Check(SyncWatchCopy.Text("library", "unknown") == SyncWatchCopy.Text("library"), "locale fallback");
        Check(SyncWatchCopy.Text("unknown-key", "ru") == "unknown-key", "copy key fallback");
        Check(Enum.GetNames<LibraryVisualState>().Select(name => char.ToLowerInvariant(name[0]) + name[1..]).SequenceEqual(SyncWatchCopy.GalleryStates), "state contract");
        var output = Environment.GetEnvironmentVariable("SYNCWATCH_DESIGN_SCREENSHOTS");
        if (output is not null) Directory.CreateDirectory(output);
        foreach (var theme in new[] { "dark", "light" })
        {
            application.Resources.MergedDictionaries.Add((ResourceDictionary)dictionary["theme." + theme]);
            foreach (var language in new[] { "en", "ru" })
                foreach (var state in Enum.GetValues<LibraryVisualState>())
                    foreach (var (width, height) in new[] { (1120, 760), (800, 600) })
                    {
                        var fixture = LibraryPresentation.Gallery(state);
                        var workspace = new LibraryWorkspace();
                        workspace.Render(fixture with { SelectedId = fixture.Entries.Count > 0 ? "1" : null }, language);
                        workspace.Width = width; workspace.Height = height;
                        workspace.Measure(new Size(width, height));
                        workspace.Arrange(new Rect(0, 0, width, height));
                        workspace.UpdateLayout();
                        var start = Descendants<Button>(workspace).FirstOrDefault(b => AutomationProperties.GetAutomationId(b) == "library.startWatching");
                        Check(start is null || start.IsEnabled == (state == LibraryVisualState.Selected), "rendered Start capability");
                        foreach (var button in Descendants<Button>(workspace).Where(b => AutomationProperties.GetAutomationId(b) == "library.openCall"))
                            Check(!button.IsEnabled, "unavailable call stays disabled");
                        if (state == LibraryVisualState.Selected)
                        {
                            string? actualSelection = null;
                            workspace.ActionRequested += (action, value) => { if (action == "selectMovie") actualSelection = value; };
                            var search = Descendants<TextBox>(workspace).Single();
                            search.Text = "very long";
                            workspace.UpdateLayout();
                            var movie = Descendants<Button>(workspace).Single(b => AutomationProperties.GetAutomationId(b).StartsWith("library.movie.", StringComparison.Ordinal));
                            movie.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
                            Check(actualSelection == "1", "search and row action");
                            // Selection rerenders must preserve the local query.
                            workspace.Render(workspace.Presentation, language); workspace.UpdateLayout();
                            Check(Descendants<TextBox>(workspace).Single().Text == "very long", "query survives selection render");
                            Descendants<TextBox>(workspace).Single().Text = "";
                            // Reset before capturing the full gallery fixture.
                            workspace.Render(fixture with { SelectedId = "1" }, language); workspace.UpdateLayout();
                        }
                        var image = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32);
                        image.Render(workspace);
                        var pixels = new byte[width * height * 4]; image.CopyPixels(pixels, width * 4, 0);
                        Check(pixels[3] == 255 && pixels.Any(value => value != pixels[0]), "nonblank native render");
                        var expectedBackground = ((SolidColorBrush)application.Resources["theme.gradientStart.brush"]).Color;
                        Check(Math.Abs(pixels[0] - expectedBackground.B) <= 1 && Math.Abs(pixels[1] - expectedBackground.G) <= 1 && Math.Abs(pixels[2] - expectedBackground.R) <= 1, "rendered gradient follows theme");
                        foreach (var title in Descendants<TextBlock>(workspace).Where(t => AutomationProperties.GetAutomationId(t) == "library.selectedTitle"))
                            Check(title.ActualHeight <= SyncWatchTokens.TypeTitleSize * 2.4 + 1, "long title stays within two lines");
                        if (output is not null)
                        {
                            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(image));
                            using var file = File.Create(Path.Combine(output, $"{state}-{theme}-{language}-{width}x{height}.png")); encoder.Save(file);
                        }
                    }
            application.Resources.MergedDictionaries.Remove((ResourceDictionary)dictionary["theme." + theme]);
        }
        Console.WriteLine("Verified Library capabilities, search/selection events and 40 native theme/language/state/viewport renders");
    }

    private static void Check(bool condition, string name)
    {
        if (!condition)
        {
            throw new InvalidOperationException("Design resource mismatch: " + name);
        }
    }
}
