using System.Windows;
using System.Windows.Controls;

namespace SyncWatch.Design;

internal static class SelectionMenuFixtures
{
    public static SelectionMenuPresentation Presentation(string kind, string state, string language = "en")
    {
        var definition = SyncWatchSelectionMenu.Kinds.Single(k => k.Id == kind);
        int count = state == "empty" ? 0 : state == "longList" ? SyncWatchSelectionMenu.GalleryEntryCount : 3;
        var entries = Enumerable.Range(0, count).Select(i =>
        {
            string label = SyncWatchCopy.Text(state == "longList" ? "selectionFixtureLong" : definition.Label, language);
            return new SelectionMenuEntry($"item{i}", label + " " + (i + 1).ToString(System.Globalization.CultureInfo.InvariantCulture), i != 2);
        }).ToArray();
        return new() { Kind = kind, SourceID = "fixture-" + kind, Revision = 1, Entries = entries, SelectedID = entries.FirstOrDefault()?.Id, Enabled = state != "readOnly" };
    }
}

// In-memory gallery. Layout and fixture placement are common declarations.
public sealed class SelectionMenuGallery : UserControl
{
    private readonly DesignSurface gallery = new("Gallery"), fixture = new("selectionFixture");
    private readonly SelectionMenu menu = new();
    private string kind = "playlist", state = "available", language = "en", lastAction = "";
    private string? selectedID;
    private long revision = 1;
    private bool dark = true;
    private ResourceDictionary? selectedTheme;
    public SelectionMenuGallery()
    {
        Content = gallery;
        gallery.Slots["galleryContent"] = fixture;
        fixture.Slots["selectionFixtureContent"] = menu;
        menu.SelectionRequested += request =>
        {
            selectedID = request.EntryID;
            revision++;
            lastAction = request.Scope + ":" + request.Action;
            Refresh();
        };
        gallery.EventRequested += e =>
        {
            if (e.Action != "gallery" || e.Value is null) return;
            switch (e.Payload)
            {
                case "kind": kind = e.Value; break;
                case "state": state = e.Value; break;
                case "language": language = e.Value; break;
                case "dark": dark = e.Value == "true"; break;
                default: return;
            }
            selectedID = null;
            revision++;
            Refresh();
        };
        Refresh();
    }
    private static DesignContext Choice(string id, string value, IEnumerable<string> options) => new()
    {
        Values = new()
        {
            ["id"] = id,
            ["label"] = "gallery" + char.ToUpperInvariant(id[0]) + id[1..],
            ["kind"] = "choice",
            ["value"] = value,
            ["editable"] = "true",
        },
        Collections = new() { ["options"] = options.Select(o => new DesignContext { Values = new() { ["id"] = o, ["label"] = o } }).ToArray() },
    };
    private void Refresh()
    {
        if (selectedTheme is not null) Resources.MergedDictionaries.Remove(selectedTheme);
        var source = Application.Current.Resources.MergedDictionaries.First(d => d.Contains("theme.dark"));
        selectedTheme = (ResourceDictionary)source[dark ? "theme.dark" : "theme.light"]; Resources.MergedDictionaries.Add(selectedTheme);
        var p = SelectionMenuFixtures.Presentation(kind, state, language) with { Revision = revision };
        if (selectedID is not null && p.Entries.Any(e => e.Id == selectedID)) p = p with { SelectedID = selectedID };
        menu.Render(p, language); fixture.Render(new(), language);
        gallery.Render(new()
        {
            Values = new() { ["lastAction"] = lastAction },
            Collections = new()
            {
                ["galleryControls"] =
                [
                    Choice("kind", kind, SyncWatchSelectionMenu.Kinds.Select(k => k.Id)),
                    Choice("state", state, SyncWatchSelectionMenu.States),
                    Choice("language", language, ["en", "ru"]),
                    new()
                    {
                        Values = new()
                        {
                            ["id"] = "dark", ["label"] = "galleryDark", ["kind"] = "boolean",
                            ["value"] = dark ? "true" : "false", ["editable"] = "true",
                        },
                    },
                ],
            },
        }, language);
    }
}
