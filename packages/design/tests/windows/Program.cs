using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using SyncWatch.Design;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "design-manifest.json")));
        var manifest = document.RootElement;
        var application = new Application();
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

            Check(((SolidColorBrush)panel.Background).Color == (Color)dictionary[theme.Value.GetProperty("background").GetString()!], "DynamicResource theme change");
            count++;
        }

        Console.WriteLine(string.Create(CultureInfo.InvariantCulture, $"Verified {count} compiled C#/WPF resources and theme assertions"));
    }

    private static void Check(bool condition, string name)
    {
        if (!condition)
        {
            throw new InvalidOperationException("Design resource mismatch: " + name);
        }
    }
}
