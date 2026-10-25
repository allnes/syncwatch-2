using System.Windows;
using Microsoft.Win32;

namespace SyncWatch;

public partial class App : Application
{
    private ResourceDictionary? selectedTheme;
    internal AppearancePreferences? Preferences { get; private set; }
    internal MediaConfiguration? Media { get; private set; }
    internal string StatePath { get; private set; } = AppearancePreferences.DefaultPath;

    protected override void OnStartup(StartupEventArgs e)
    {
        if (!e.Args.Contains("--selection-menu-gallery") && !e.Args.Contains("--call-gallery") && !e.Args.Contains("--design-gallery") && !e.Args.Contains("--settings-gallery") && !e.Args.Contains("--player-gallery") && !e.Args.Contains("--player-settings-gallery"))
        {
            int index = Array.IndexOf(e.Args, "--state-directory");
            if (index >= 0 && index + 1 < e.Args.Length) StatePath = System.IO.Path.Combine(System.IO.Path.GetFullPath(e.Args[index + 1]), "local-state.json");
            Preferences = new AppearancePreferences(new Domain.FileLocalStateStore(StatePath));
            Media = MediaConfiguration.Read(e.Args);
        }
        ApplySystemTheme();
        SystemEvents.UserPreferenceChanged += OnUserPreferenceChanged;
        base.OnStartup(e);
    }

    protected override void OnExit(ExitEventArgs e)
    {
        SystemEvents.UserPreferenceChanged -= OnUserPreferenceChanged;
        base.OnExit(e);
    }

    private void OnUserPreferenceChanged(object sender, UserPreferenceChangedEventArgs e)
    {
        Dispatcher.BeginInvoke(new Action(ApplySystemTheme));
    }

    internal void ApplySystemTheme()
    {
        using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
        var selected = Preferences?.State.Preferences.Theme ?? "system";
        var dark = selected == "dark" || (selected == "system" && key?.GetValue("AppsUseLightTheme") is int value && value == 0);
        var tokens = Resources.MergedDictionaries[0];
        if (selectedTheme is not null)
        {
            Resources.MergedDictionaries.Remove(selectedTheme);
        }

        selectedTheme = (ResourceDictionary)tokens[dark ? "theme.dark" : "theme.light"];
        Resources.MergedDictionaries.Add(selectedTheme);
    }
}
