using System.IO;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using SyncWatch.Design;
using SyncWatch.Library;

namespace SyncWatch;

internal interface IExternalTrackChoosing
{
    Task<LocalFileAccess?> ChooseAsync(string kind, string language, CancellationToken cancellation);
    void Cancel();
}

/// <summary>Owns one Windows shell dialog, including its documented cancellation/COM lifetime.</summary>
internal sealed class ExternalTrackPicker(Func<Window?> owner) : IExternalTrackChoosing
{
    private const int Cancelled = unchecked((int)0x800704C7);
    private const uint FileSystemPathName = 0x80058000; // SIGDN_FILESYSPATH
    [Flags]
    private enum FileOptions : uint
    {
        NoChangeDirectory = 0x8,
        ForceFileSystem = 0x40,
        PathMustExist = 0x800,
        FileMustExist = 0x1000,
    }
    private IFileDialog? active;
    public async Task<LocalFileAccess?> ChooseAsync(string kind, string language, CancellationToken cancellation)
    {
        // Yield before the modal loop so the coordinator records its pending operation first.
        await Task.Yield();
        cancellation.ThrowIfCancellationRequested();
        var window = owner() ?? throw new InvalidOperationException("external-picker-owner");
        window.Dispatcher.VerifyAccess();
        var filter = SyncWatchSelectionMenu.ExternalFileFilters.Single(item => item.Kind == kind);
        if (active is not null) throw new InvalidOperationException("external-picker-active");
        var type = Type.GetTypeFromCLSID(new Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7"), throwOnError: true)!;
        var dialog = (IFileDialog)Activator.CreateInstance(type)!;
        active = dialog;
        try
        {
            dialog.GetOptions(out uint options);
            dialog.SetOptions(options | (uint)(FileOptions.ForceFileSystem | FileOptions.FileMustExist | FileOptions.PathMustExist | FileOptions.NoChangeDirectory));
            string label = SyncWatchCopy.Text(filter.Label, language);
            dialog.SetTitle(label);
            dialog.SetFileTypes(1, [new() { Name = label, Pattern = string.Join(";", filter.Extensions.Select(x => "*." + x)) }]);
            using var registration = cancellation.Register(() => window.Dispatcher.InvokeAsync(() =>
            {
                if (ReferenceEquals(active, dialog)) Cancel();
            }));
            cancellation.ThrowIfCancellationRequested();
            int result = dialog.Show(new WindowInteropHelper(window).Handle);
            cancellation.ThrowIfCancellationRequested();
            if (result == Cancelled) return null;
            Marshal.ThrowExceptionForHR(result);
            dialog.GetResult(out IShellItem item);
            try
            {
                item.GetDisplayName(FileSystemPathName, out nint pointer);
                try
                {
                    string file = Marshal.PtrToStringUni(pointer) ?? throw new IOException("external-local-file");
                    return LocalFileAccess.Selected(file);
                }
                finally { Marshal.FreeCoTaskMem(pointer); }
            }
            finally { Marshal.FinalReleaseComObject(item); }
        }
        finally
        {
            active = null;
            Marshal.FinalReleaseComObject(dialog);
        }
    }
    public void Cancel() { active?.Close(Cancelled); }

    // Public Windows SDK vtables: IModalWindow/IFileDialog and IShellItem.
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct FilterSpec
    {
        [MarshalAs(UnmanagedType.LPWStr)] public string Name;
        [MarshalAs(UnmanagedType.LPWStr)] public string Pattern;
    }
    [ComImport, Guid("42F85136-DB7E-439C-85F1-E4075D135FC8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IFileDialog
    {
        [PreserveSig] int Show(nint owner);
        void SetFileTypes(uint count, [In, MarshalAs(UnmanagedType.LPArray, SizeParamIndex = 0)] FilterSpec[] filters);
        void SetFileTypeIndex(uint index);
        void GetFileTypeIndex(out uint index);
        void Advise(nint events, out uint cookie);
        void Unadvise(uint cookie);
        void SetOptions(uint options);
        void GetOptions(out uint options);
        void SetDefaultFolder(nint item);
        void SetFolder(nint item);
        void GetFolder(out nint item);
        void GetCurrentSelection(out nint item);
        void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
        void GetFileName(out nint name);
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
        void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
        void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
        void GetResult([MarshalAs(UnmanagedType.Interface)] out IShellItem item);
        void AddPlace(nint item, uint placement);
        void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string extension);
        [PreserveSig] int Close(int result);
        void SetClientGuid(in Guid guid);
        void ClearClientData();
        void SetFilter(nint filter);
    }
    [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IShellItem
    {
        void BindToHandler(nint context, in Guid handler, in Guid type, out nint result);
        void GetParent(out nint parent);
        void GetDisplayName(uint nameType, out nint name);
        void GetAttributes(uint mask, out uint attributes);
        void Compare(nint other, uint hint, out int order);
    }
}
