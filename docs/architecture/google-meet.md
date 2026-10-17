# Google Meet integration

SyncWatch hosts the call in a separate application-owned window. The application manages its window frame and lifecycle; a real Google Meet surface handles the meeting. Integration feasibility and capabilities must be established on both supported platforms before release.

## Provider interfaces

| Interface or constraint | Architectural consequence |
|---|---|
| Meet REST API manages spaces and conference metadata | It can support meeting setup but does not supply a native two-way call renderer. [REST overview](https://developers.google.com/workspace/meet/api/guides/overview) |
| `spaces.create` creates a meeting space | Automated creation is optional after OAuth setup; accepting an existing Meet URL is an initial workflow. [API reference](https://developers.google.com/workspace/meet/api/reference/rest/v2/spaces/create) |
| Meet Media API consumes media and participant metadata, with new preview registrations closed | It is not a required two-way client SDK or an assumed product dependency. [Media API overview](https://developers.google.com/workspace/meet/media-api/guides/overview) |
| Meet add-ons run applications inside Meet | They do not establish that Meet can be embedded in a native application. [Add-ons overview](https://developers.google.com/workspace/meet/add-ons/guides/overview) |
| Google lists supported browsers | Embedded hosts still require their own feasibility test. [Meet requirements](https://support.google.com/meet/answer/7317473?hl=en) |
| OAuth restricts embedded user agents | API authorization uses a supported external-user-agent flow. An API token does not automatically establish a Meet web session. [Native OAuth](https://developers.google.com/identity/protocols/oauth2/native-app), [embedded webview policy](https://developers.googleblog.com/upcoming-security-changes-to-googles-oauth-20-authorization-endpoint-in-embedded-webviews/) |

These interfaces do not establish a complete native call-control contract. The implementation must verify each required capability instead of inferring it from successful navigation.

## Call window host

On macOS, the candidate is a Swift/AppKit-owned `NSWindow` with top-level WKWebView navigation. On Windows, the open-source candidate is a C# WPF-owned window backed by CEF/CefSharp. Final host selection follows the [source dependency policy](dependencies.md) and the feasibility gate.

The native shell owns move, resize, pin, minimize, restore, fullscreen, and failure presentation. The content area displays Google Meet. Do not depend on iframe embedding, user-agent spoofing, imported browser cookies, or unstable DOM selectors for production controls.

Provider content receives only the permissions necessary for the call. Do not expose native file access, playback control, or room credentials to the provider page. Use an application-specific browser profile and constrain privileged navigation. Handle account access failures explicitly; API authorization alone does not solve web authentication.

## State and capabilities

The host can represent `idle`, `opening`, `webSurfaceReady`, `userActionRequired`, `failed`, and `closed`. Represent joined state, camera/microphone state, remote video availability, and speaking activity only when the integration provides a reliable signal.

| Product capability | Required evidence |
|---|---|
| Open and restore the call window | Native window lifecycle works independently of meeting navigation |
| Two-way camera and microphone | Successful participation with the supported account types and actual devices |
| Device selection and native media controls | Working provider integration for every exposed action |
| Hangup and close | Capture and participation stop, including when the window closes |
| Remote video | A usable video presentation within the application-owned window |
| Independent call volume | Only the intended call output changes |
| Remote-speaking notification | A reliable signal for movie ducking |
| Camera quality | Actual selectable provider/host capability |
| Compact call layout | A usable minimum viewport with functioning meeting controls |

Capabilities such as `canObserveJoin`, `canMuteFromNativeUI`, `canSelectDevicesFromNativeUI`, `canSetCallVolume`, `canObserveRemoteSpeaking`, and `canConfirmHangup` default to false until proven. Missing capabilities remain unmet requirements; an ineffective UI action is not an implementation.

## Feasibility gate G1

Test the selected hosts in interactive macOS and Windows sessions:

1. Open a separate application-owned window with top-level Meet navigation.
2. Verify signed-in and guest participation separately for the supported account types.
3. Establish two-way camera/microphone media, switch devices, and restore the window after minimization.
4. Check each exposed control and observable capability through a reliable integration path.
5. Verify hangup, close, capture release, reconnect, expired meetings, and denied permissions.
6. Run a local movie with Syncplay between both devices during the call and verify audio isolation and playback responsiveness.

Record host versions, account categories, and the capability result in the relevant implementation review, excluding credentials, meeting links, cookies, and private participant content. Finalize the browser dependency graph after selecting a viable host.

If the in-application host or a required capability fails this gate, release acceptance remains blocked for the affected requirement. Any alternative window model, provider, or reduced capability set requires an explicit product decision.
