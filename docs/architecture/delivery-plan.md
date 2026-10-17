# План реализации и приёмки

Это план будущей реализации. Создание документов и source submodules выполнено; ни один пункт runtime приёмки ниже ещё не закрыт.

## Порядок законченных шагов

| Этап | Результат отдельного шага | Доказательство завершения |
|---|---|---|
| P0. Зафиксировать baseline | Read-only prototype audit, design tokens, functional matrix, provenance | Исходный commit и SHA-256, чистый исходный checkout; полный visual/runtime baseline ещё нужно доснять |
| P1. Проверить Meet раньше основного UI | Минимальные Swift/C# app-owned call windows и отчёт G1 | Signed-in и guest сценарии проверены отдельно; реальный Mac ↔ Windows call; список capabilities и gaps |
| P2. Материализовать toolchains и source graph | Точный .NET SDK, Swift settings, Node/Python toolchains, все transitive source submodules для выбранных компонентов | Никаких floating dependencies; воспроизводимый offline component build; provenance binaries и notices |
| P3. Общая библиотека дизайна | Style Dictionary custom formatters, Swift resources, C#/XAML resources; галерея компонентов | Одинаковые IDs/значения, deterministic generation, dark/light/RU/EN snapshots; source drift check |
| P4. VLC на двух ОС | Нативный video host с player chrome, tracks и preview | Реальные files, HW decode evidence, Windows overlay/DPI/input/fullscreen; ни один player setting не no-op |
| P5. Syncplay bridge | Headless helper с formal IPC schema и upstream client engine | Import/init без GUI, native↔official client interoperability, reconnect, duplicate/stale commands, child teardown |
| P6. RoomMetadata и каталог | Catalog exchange, media identity, session generation, missing file, Meet URI | Тесты rooms/authorization/snapshot/order/late join; никакой передачи полных local paths или playback control по WSS |
| P7. Собрать продуктовые сценарии | Library → Start → Player → Continue/End, отдельный Meet shell, все preferences | F01–F25 проверены на Mac и Windows, визуальные сравнения и сохранение настроек |
| P8. Упаковка | Подписанный macOS bundle и Windows package, provenance и dependencies notices | Clean-machine launch, source pin correspondence, first-run permissions и повторный запуск без остаточных processes/capture |

P1 — маленький эксперимент до полной реализации, чтобы не построить всё приложение на неподтверждённом предположении о Meet. Если gate не проходит, завершить независимые части проектирования и предъявить конкретный gap для продуктового решения. Не считать ограниченную демоверсию сохранением всего функционала.

Для каждого этапа: сфокусированный commit → соответствующие проверки → push. Крупный этап делить на самостоятельные reviewable результаты; не коммитить случайные intermediate поломки как законченный шаг.

## Матрица автоматических проверок

| Уровень | Существенные сценарии |
|---|---|
| Design generator | Unknown type/reference, цвет/alpha, pt/DIP conversion, повторная генерация без diff, одинаковые IDs и manifest hash |
| Domain на Swift и C# | Start/Continue/End, repeated actions, paused seek, foreign generation, late join, missing/mismatched edition, cancellation |
| Bridge contract | Версии, frame bounds, partial reads, duplicate IDs, ordered writes, timeout, stale run, crash/EOF, не смешивать logs и JSON |
| RoomMetadata | Isolation rooms, access token expiry/revocation, conflicting selection ordering, snapshot gap/replay, reconnect и bounded catalog batches |
| VLC adapter | Actual position после seek, buffering, tracks, внешние subtitles/audio, preview без влияния на main player, release callbacks |
| Platform integration | Security-scoped grants, DPI/focus/fullscreen/window ownership, settings persistence, safe helper teardown |

Одни только mocked callbacks недостаточны для утверждений о codec support, video rendering или Meet. Тестовый framework и manifest добавляются вместе с первым исполняемым компонентом; его build/test команды документируются по фактической реализации, а не выдумываются сейчас.

## Физическая приёмка Mac ↔ Windows

1. Один согласованный media fixture на двух машинах: обычный 1080p и реальный 4K с audio/subtitles. Зафиксировать SHA-256, duration, codec, frame rate и build IDs вне публичных movie artifacts.
2. Запустить приложения в интерактивных desktop сессиях. Проверить Library, grants, theme/language/settings и видео, затем соединить Syncplay.
3. Play, pause и seek с обеих сторон, включая быстрые competing seeks; late join, отсутствие/подмена файла, возврат в библиотеку, Continue, End.
4. Контролируемый сетевой разрыв Syncplay и reconnect; отдельно разрыв metadata и Meet. Старый seek не должен возобновить закончившуюся session.
5. Meet: реальные camera/mic в обе стороны, управление устройствами, допустимый hangup, minimize/restore и отказ permissions. RDP camera/mic redirection не заменяет проверку физических устройств.
6. Повторить совместную нагрузку movie+call. Измерить actual playback positions, buffering/dropped frames, CPU/GPU/RSS, input latency и time-to-first-frame. Выполнить stop/start и убедиться, что idle ресурсы освобождены.
7. Закрыть app/call и повторить запуск. Нет orphan helpers, hidden media capture, занятых transient ports, stale bookmarks и потерянных preferences.

Предварительная инженерная цель для drift — p95 не выше 250 ms после стабилизации, но это не заявленный результат и не обещание upstream. Метод измерения должен сравнивать samples на согласованной временной базе с учётом clock offset/RTT; два несинхронизированных wall-clock logs не доказывают drift. На settle/seek/buffering отдельно задаются наблюдаемые интервалы. Пороги CPU/GPU/RSS фиксируются после реального baseline на тех же файлах, hardware и power settings.

## Где проверять

- Mac: локальный Apple Silicon Mac, Xcode/Swift доступны; privacy prompts и signing проверять при реализации.
- Windows: существующий host `win-dev`, указанный пользователем RDP profile остаётся локальным в каталоге devices. SSH reachability проверена, интерактивное подключение для новой версии пока не выполнено.
- На Windows сейчас есть .NET 8 runtime, но нет .NET SDK. Перед C# build установить и закрепить выбранный SDK; текущая архитектурная задача не меняла машину и не устанавливала software.
- Backend staging ещё не выбран/не развёрнут. Сначала локальная изолированная комната, затем согласованная сеть для двух устройств; существующий LiveKit deployment для новой архитектуры не требуется.

Наличие RDP-файла, успешный SSH, submodule checkout или удачный unit test не закрывают физическую media приёмку.
