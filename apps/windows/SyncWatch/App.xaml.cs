using System.Windows;
using Microsoft.Win32;

namespace SyncWatch;

public partial class App : Application
{
    private ResourceDictionary? selectedTheme;

    protected override void OnStartup(StartupEventArgs e)
    {
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

    private void ApplySystemTheme()
    {
        using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
        var dark = key?.GetValue("AppsUseLightTheme") is int value && value == 0;
        var tokens = Resources.MergedDictionaries[0];
        if (selectedTheme is not null)
        {
            Resources.MergedDictionaries.Remove(selectedTheme);
        }

        selectedTheme = (ResourceDictionary)tokens[dark ? "theme.dark" : "theme.light"];
        Resources.MergedDictionaries.Add(selectedTheme);
    }
}
