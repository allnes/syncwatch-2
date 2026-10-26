using System.Windows.Threading;

internal static class RoomDispatcherChecks
{
    internal static async Task RunAsync(Func<Task> checks)
    {
        var completed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var thread = new Thread(() =>
        {
            var dispatcher = Dispatcher.CurrentDispatcher;
            SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext(dispatcher));
            Exception? failure = null;
            dispatcher.InvokeAsync(async () =>
            {
                try { await checks(); }
                catch (Exception error) { failure = error; }
                finally { dispatcher.BeginInvokeShutdown(DispatcherPriority.Background); }
            });
            Dispatcher.Run();
            if (failure is null) completed.SetResult(); else completed.SetException(failure);
        });
        thread.SetApartmentState(ApartmentState.STA); thread.Start();
        try { await completed.Task; }
        finally { thread.Join(); }
    }
}
