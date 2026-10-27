using System.Net;
using System.Net.WebSockets;
using System.Text;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using SyncWatch.Room;

internal static class EventStreamChecks
{
    internal static async Task RunAsync(RoomBootstrap bootstrap)
    {
        var builder = WebApplication.CreateSlimBuilder();
        builder.Logging.ClearProviders();
        builder.WebHost.ConfigureKestrel(options => options.Listen(IPAddress.Loopback, 0));
        await using var server = builder.Build();
        server.UseWebSockets();
        server.Run(async context =>
        {
            using var socket = await context.WebSockets.AcceptWebSocketAsync();
            string scenario = context.Request.Path.Value!.Split('/')[3];
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(10));
            switch (scenario)
            {
                case "abrupt": context.Abort(); break;
                case "closed":
                    await socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "", deadline.Token);
                    break;
                case "binary":
                    await socket.SendAsync(new byte[] { 1 }, WebSocketMessageType.Binary, true, deadline.Token);
                    break;
                case "malformed":
                    await socket.SendAsync(Encoding.UTF8.GetBytes("not-json"), WebSocketMessageType.Text, true, deadline.Token);
                    break;
                case "oversized":
                    await socket.SendAsync(new byte[65537], WebSocketMessageType.Text, true, deadline.Token);
                    break;
                case "limit":
                    // A full-size valid message must drain before the close reason is exposed.
                    await socket.SendAsync(Encoding.UTF8.GetBytes("{}" + new string(' ', 65534)), WebSocketMessageType.Text, true, deadline.Token);
                    await socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "", deadline.Token);
                    break;
                default: throw new InvalidOperationException("Unknown event-stream scenario");
            }
        });
        await server.StartAsync();
        try
        {
            string address = server.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single();
            foreach (var (scenario, expected) in new[] { ("abrupt", "transport"), ("closed", "closed"),
                ("binary", "malformed"), ("malformed", "malformed"), ("oversized", "frameTooLarge"), ("limit", "closed") })
            {
                using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(10));
                await using var client = new RoomClient(new(address));
                var admission = new RoomAdmission(scenario, "member-owner", new(new string('A', 64)), null,
                    DateTimeOffset.UtcNow.AddMinutes(1), bootstrap);
                var events = await client.OpenEventsAsync(admission, deadline.Token);
                if (scenario == "limit" && (await events.ReceiveAsync(deadline.Token)).Length != 65536)
                    throw new Exception("Full-size event was lost on close");
                for (int repeat = 0; repeat < 2; repeat++)
                {
                    try { _ = await events.ReceiveAsync(deadline.Token); }
                    catch (RoomProtocolException error) when (error.Message == expected) { continue; }
                    throw new Exception($"Event stream did not preserve {scenario} reason {expected}");
                }
            }
            Console.WriteLine("SYNCWATCH_ROOM_EVENT_STREAM_OK transport, close, malformed, oversized, exact limit");
        }
        finally { await server.StopAsync(); }
    }
}
