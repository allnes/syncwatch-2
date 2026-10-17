# SyncWatch development instructions

- Keep project code in this checkout. The reference prototype at `/Users/anesterov/repos/syncwatch-opt/syncwatch` is read-only for this project.
- Store all project documentation in `docs/`. The workspace path `/Users/anesterov/repos/salo-syncwatch/docs` links to this directory so documentation is versioned here.
- Preserve the prototype's design and behavior. Record provider limitations and unverified parity explicitly before implementing replacements.
- Use Swift for Apple clients, C# for Windows, VLC/libVLC for playback, Syncplay for playback synchronization, and Google Meet for calls in a separate app-owned window. The platform-neutral design library is `packages/design/`, using Apache 2.0 Style Dictionary to generate native resources; preserve the prototype's design. Follow `docs/architecture/README.md` and its explicit unresolved feasibility gates.
- Add every external source dependency as a pinned Git submodule under `3rdparty/`; do not copy vendor sources or silently fetch runtime dependencies through package managers. Record transitive dependencies and SDK/runtime exceptions in `docs/architecture/dependencies.md`.
- Never commit credentials, meeting invitations, local device configuration, binaries, caches, or build outputs.
- Commit and push each completed meaningful change. Validate changed files and report checks that have not run.
- This checkout currently contains architecture documentation and dependency sources, not a runnable application. Add reproducible build and test instructions with the first implementation.
