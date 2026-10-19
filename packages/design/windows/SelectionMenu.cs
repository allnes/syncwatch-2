using System.Windows.Controls;

namespace SyncWatch.Design;

public sealed class SelectionMenu : UserControl
{
    public SelectionMenuPresentation Presentation { get; private set; } = new();
    public event Action<SelectionMenuRequest>? SelectionRequested;
    private readonly DesignSurface surface = new("SelectionMenu");
    public SelectionMenu()
    {
        Content = surface;
        surface.EventRequested += e =>
        {
            if (e.Action == "selectEntry" && e.Value is string id && e.Payload is string token)
                Presentation.Dispatch(id, token, request => SelectionRequested?.Invoke(request));
        };
        Render(new());
    }
    public void Render(SelectionMenuPresentation presentation, string language = "en")
    {
        Presentation = presentation;
        surface.Render(SelectionMenuBindings.Context(presentation), language);
    }
}

internal static class SelectionMenuBindings
{
    public static DesignContext Context(SelectionMenuPresentation p)
    {
        var entries = p.IsValid ? p.Entries : [];
        return new()
        {
            Values = new()
            {
                ["kind"] = p.Kind,
                ["menuLabel"] = p.Definition?.Label ?? "selectionUnavailable",
                ["contextToken"] = p.ContextToken,
                ["entryCount"] = entries.Count.ToString(System.Globalization.CultureInfo.InvariantCulture),
                ["hasEntries"] = entries.Count > 0 ? "true" : "false",
                ["emptyLabel"] = p.IsValid ? "selectionEmpty" : "selectionUnavailable",
            },
            Collections = new()
            {
                ["entries"] = entries.Select(entry => new DesignContext
                {
                    Values = new()
                    {
                        ["id"] = entry.Id,
                        ["label"] = entry.Label,
                        ["selected"] = p.SelectedID == entry.Id ? "true" : "false",
                        ["enabled"] = p.Enabled && entry.Enabled ? "true" : "false",
                    },
                }).ToArray(),
            },
        };
    }
}
