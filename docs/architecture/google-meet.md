# Google Meet integration

The SyncWatch call architecture uses a separate application-owned window. The application manages its frame and lifecycle; a Google Meet surface handles the meeting. Call hosting is not implemented in the current native shells.

## Provider interfaces

| Interface or constraint | Architectural consequence |
|---|---|
| Meet REST API manages spaces and conference metadata | It can support meeting setup but does not supply a native two-way call renderer. [REST overview](https://developers.google.com/workspace/meet/api/guides/overview) |
| `spaces.create` creates a meeting space | Automated creation is optional after OAuth setup; accepting an existing Meet URL is an initial workflow. [API reference](https://developers.google.com/workspace/meet/api/reference/rest/v2/spaces/create) |
| Meet Media API consumes media and participant metadata, with new preview registrations closed | It is not a required two-way client SDK or an assumed product dependency. [Media API overview](https://developers.google.com/workspace/meet/media-api/guides/overview) |
| Meet add-ons run applications inside Meet | They do not establish that Meet can be embedded in a native application. [Add-ons overview](https://developers.google.com/workspace/meet/add-ons/guides/overview) |
| Google lists supported browsers | Embedded hosts still require their own feasibility test. [Meet requirements](https://support.google.com/meet/answer/7317473?hl=en) |
| OAuth restricts embedded user agents | API authorization uses a supported external-user-agent flow. An API token does not automatically establish a Meet web session. [Native OAuth](https://developers.google.com/identity/protocols/oauth2/native-app), [embedded webview policy](https://developers.googleblog.com/upcoming-security-changes-to-googles-oauth-20-authorization-endpoint-in-embedded-webviews/) |

These interfaces do not supply a complete native call-control contract. Successful navigation alone does not establish call participation or native control support.

## Call window host

On macOS, the candidate is a Swift/AppKit-owned `NSWindow` with top-level WKWebView navigation. On Windows, the open-source candidate is a C# WPF-owned window backed by CEF/CefSharp. Browser-host compatibility remains unresolved; CEF/CefSharp also needs a complete [source dependency graph](dependencies.md).

The native shell owns move, resize, pin, minimize, restore, fullscreen, and failure presentation. The content area displays Google Meet. Do not depend on iframe embedding, user-agent spoofing, imported browser cookies, or unstable DOM selectors for production controls.

Provider content receives only the permissions necessary for the call. Do not expose native file access, playback control, or room credentials to the provider page. Use an application-specific browser profile and constrain privileged navigation. Handle account access failures explicitly; API authorization alone does not solve web authentication.

## State and capabilities

The host can represent `idle`, `opening`, `webSurfaceReady`, `userActionRequired`, `failed`, and `closed`. Represent joined state, camera/microphone state, remote video availability, and speaking activity only when the integration provides a reliable signal.

| Call behavior | Host responsibility |
|---|---|
| Open and restore the call window | Native window lifecycle independent of meeting navigation |
| Two-way camera and microphone | Provider participation and device capture |
| Device selection and native media controls | Available provider interfaces |
| Hangup and close | Capture and participation stop, including when the window closes |
| Remote video | A usable video presentation within the application-owned window |
| Local camera thumbnail | Compact actual self-view alongside remote video, with active, disabled, denied, and unavailable states |
| Initial camera state | Enabled camera starts on first join with permission granted, without an off/on workaround |
| Independent call volume | Zero/mute, intermediate, and full values affect only received call output; movie, microphone, other applications, and peers remain unchanged |
| Inactive call audio | No received audio before join or after hangup, close, failed join, or teardown; synchronization-room membership alone does not open audio |
| Remote-speaking notification | A reliable signal for movie ducking |
| Camera quality | Actual selectable provider/host capability |
| Compact call layout | A usable minimum viewport with functioning meeting controls |

Capabilities such as `canObserveJoin`, `canMuteFromNativeUI`, `canSelectDevicesFromNativeUI`, `canSetCallVolume`, `canObserveRemoteSpeaking`, and `canConfirmHangup` default to false. Only a reliable provider integration can advertise support.

The existing six-field capability schema has no local-preview or initial-camera fields. Native actions for these features need an explicit versioned capability boundary. A loaded page or open audio path is not equivalent to a joined call.

## Known limitations

Both browser hosts are candidates. Embedded account access, guest participation, two-way media, native controls, independent call volume, and reliable hangup remain unresolved. Google-supported browser compatibility does not automatically extend to embedded WebKit or CEF hosts.
