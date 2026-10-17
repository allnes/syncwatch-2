# Проверки архитектурного этапа

Дата: 17 октября 2026 года. Этот документ разделяет выполненную инспекцию и будущую проверку новой реализации.

## Подтверждено в этой сессии

| Проверка | Наблюдение |
|---|---|
| Целевой Git checkout | `/Users/anesterov/repos/salo-syncwatch/syncwatch`, branch `main`, origin `https://github.com/allnes/syncwatch-2` |
| Документы | Workspace `docs` — относительная ссылка `syncwatch/docs`; документы включены в Git |
| Прототип | Commit `df6c0f71a5075c13c7c9af075bc76946246ccfb7`, чистое дерево при аудите; чтение исходников и существующих regression scenarios |
| Источники дизайна | 14 file hashes в `packages/design/provenance.json`; точные palette и исследованная geometry извлечены из исходников |
| Реальная синхронизация прототипа | `LiveKitSyncEngine`; Syncplay address в preferences сам по себе не выполняет синхронизацию |
| Source dependencies | Три gitlinks: Style Dictionary `v5.7.0`, Syncplay `v1.7.6`, VLC `3.0.24`; лицензии и точки API прочитаны из checkout |
| Mac toolchain | macOS 26.6.2, Xcode 27.1, Swift 6.4, target arm64; успешный вывод `sw_vers`, `xcodebuild -version`, `swift --version` |
| Windows reachability | `ssh -o BatchMode=yes -o ConnectTimeout=8 win-dev hostname` вернул `win-dev` |
| Windows toolchain | Windows 11 Pro 64-bit, version 10.0.26200; `dotnet --info`: runtime 8.0.32, **SDK отсутствует**. Git доступен |
| Provider documentation | Прочитаны официальные Google Meet/OAuth, Style Dictionary, Syncplay, VideoLAN и Microsoft WPF/.NET материалы; ссылки находятся в соответствующих документах |

Пароли, credentials, RDP profile, private invitations, meeting links и device IP в репозиторий не копировались.

## Проверка сохранённых артефактов

Финальная проверка должна подтвердить: JSON разбирается, component token references разрешаются, palette/geometry соответствует исследованным исходникам, SHA-256 provenance совпадают, Markdown links не сломаны, submodules чистые и имеют ожидаемые gitlinks, clean clone может получить pinned sources, все законченные commits доступны на origin.

Результат финальной проверки добавляется после её выполнения отдельным commit.

## Не выполнялось

- Новая Swift/C# реализация, её build/test, генерация Swift/XAML или установка транзитивных зависимостей.
- Headless Syncplay import/init и запуск нового bridge/server/RoomMetadata.
- Новая физическая двухсторонняя media validation, VLC playback на новой архитектуре или Google Meet call.
- Полная визуальная фиксация всех экранов прототипа и comparison с native renderers.
- Установка .NET SDK, открытие RDP session, изменение Windows settings или существующего prototype deployment.

Открытое старое приложение было просмотрено, но полученный snapshot не стал полным screen baseline. Исторические результаты прототипа не выдаются за проверку новой версии.
