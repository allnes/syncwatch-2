using SyncWatch.Design;

internal static class RoomAssertions
{
    internal static void Run()
    {
        void Check(bool value) { if (!value) throw new InvalidOperationException("Room draft capability/lifetime"); }
        var editor = new RoomEditor(new Dictionary<string, string> { ["username"] = "Alice", ["creationKey"] = "must not restore" });
        Check(editor.Values["creationKey"] == "" && !editor.IsValid && editor.Context.Values["can.connectRoom"] == "false");
        editor.Edit("creationKey", "creation-secret"); editor.SelectMode("createRoom"); Check(editor.Values["creationKey"] == "creation-secret");
        editor.SelectMode("joinRoom"); Check(editor.Values["creationKey"] == "" && editor.Values["username"] == "Alice");
        editor.Edit("invitation", "invitation-secret"); editor.State = "connecting";
        editor.Edit("username", "Bob"); editor.SelectMode("createRoom"); Check(editor.Values["username"] == "Alice" && editor.Mode == "joinRoom");
        editor.ClearSecrets(); Check(editor.Values["invitation"] == "");
        editor.State = "connected"; editor.Owner = false; Check(editor.Context.Values["can.copyInvitation"] == "false");
        editor.Owner = true; Check(editor.Context.Values["can.copyInvitation"] == "true");
    }
}
