# Что сохраняем из прототипа

Аудит исходников от 17 октября 2026 года. Прототип: `/Users/anesterov/repos/syncwatch-opt/syncwatch`, commit `df6c0f71a5075c13c7c9af075bc76946246ccfb7`. Рабочее дерево при проверке чистое. Контрольные суммы исследованных файлов записаны в `packages/design/provenance.json`.

Это исходная спецификация для переноса, не результат проверки нового приложения. Исходники прототипа не изменены. Полноценные эталонные скриншоты всех экранов и новый двухсторонний runtime baseline ещё предстоит снять; просмотр открытого приложения не заменяет такую проверку.

## Реальная реализация сейчас

- Flutter/Dart, собственный Material 3 theme, `media_kit`/mpv и собственные пакеты доступа к библиотеке и mpv.
- `LiveKitSyncEngine` передаёт библиотеку и команды через LiveKit data channel. Наличие `syncplay.pl:8997` в настройках не означает использование Syncplay: реализации Syncplay в `lib/services/sync_engine.dart` нет.
- LiveKit отвечает за звонок, присутствие, состояние комнаты и события речи. Его замена затрагивает больше, чем аудио и видео.

## Матрица переноса

`Сохранить` означает обязательство архитектуры. Ни одна строка не означает, что функция уже реализована в новом приложении.

| ID | Поведение прототипа и источник относительно его корня | Ответственность новой версии | Статус / проверка |
|---|---|---|---|
| F01 | Выбор локальной папки, сканирование подпапок, поиск, rescan, настройка auto refresh; `library_screen.dart`, `app.dart` | LibraryService + native picker/watcher | Сохранить; auto refresh проверить как исполняемое поведение, а не только настройку |
| F02 | MKV, MP4, AVI, MOV, M4V, WEBM, WMV, MPG, MPEG, TS, M2TS; `library_screen.dart:44` | LibraryService + VLC metadata probe | Сохранить список расширений; поддержка конкретного codec зависит от поставки VLC |
| F03 | Длительность, разрешение, аудио и субтитры из media metadata; `library_screen.dart:_probeMovie` | MediaProbe через libVLC | Сохранить, не угадывать наличие дорожек по имени |
| F04 | Дополнительные аудио/субтитры, folder movie, имена с несколькими точками; `library_file_index.dart` | LibraryIndex | Перенести правила и fixtures, проверить регистр путей на macOS |
| F05 | Сопоставление библиотек по нормализованному movieId; fingerprint — duration/resolution; `movie_item.dart` | MediaIdentity + RoomMetadata | Сохранить совместимость отображения; одинаковое имя не доказывает одинаковый монтаж |
| F06 | Партнёр online, состояние комнаты, activity; `library_screen.dart` | Syncplay presence + RoomMetadata | Отвязать от звонка; отдельные состояния connected/reconnecting |
| F07 | Start / Continue / End watching, возврат в библиотеку без уничтожения текущего player; `library_screen.dart` | WatchSessionCoordinator | Сохранить; после нового запуска active session не восстанавливается автоматически |
| F08 | Play/pause/seek, удалённый start/end, запрос текущего состояния; `sync_engine.dart`, `player_screen.dart` | SyncplayBridge + WatchSessionCoordinator | Сохранить сценарии; устаревшие и чужие команды не применяются |
| F09 | Ready-индикация и обработка отсутствующего файла; `library_screen.dart`, `sync_engine.dart` | Syncplay ready + RoomMetadata missing-media | Сохранить смысл; тексты и UI не считать доказательством working handshake |
| F10 | Таймлайн, hover preview, кэш, отмена незавершённого seek; `preview_seek.dart`, `player_screen.dart` | PreviewService: отдельный bounded decoder | Сохранить; preview никогда не двигает основной player и не отправляет Syncplay seek |
| F11 | Playlist, previous/next, смена фильма; `player_screen.dart` | WatchSessionCoordinator + local playlist | Сохранить; смена активного медиа согласуется со всеми участниками |
| F12 | Встроенные и внешние audio/subtitle tracks; `player_screen.dart` | VLCPlayerAdapter | Сохранить; выбора дорожек по нестабильному index недостаточно |
| F13 | Movie volume/mute, call volume, default/remember volume; `app.dart`, `player_screen.dart` | LocalAudioPolicy + CallProvider capability | Movie volume — обязательно; независимая громкость Meet требует проверки, не глобальная громкость браузера/ОС |
| F14 | Ducking при речи партнёра; коэффициент 0.35, release delay 280 ms; `player_screen.dart:378` | LocalAudioPolicy + remote-speaking capability | Цель сохранения; Meet не даёт подтверждённого speaking callback. Открытый вопрос интеграции |
| F15 | Клавиши ←/→ skip, Space play/pause, ↑/↓ volume ±5%, M mute, F fullscreen, Esc выход; `player_screen.dart:_handleKeyEvent` | Platform input adapter | Сохранить; не перехватывать ввод при редактировании полей и в Meet |
| F16 | Fullscreen, скрытие курсора/контролов, context menu, popovers, OSD; `player_screen.dart` | PlayerChrome + native window manager | Сохранить на двух ОС и при DPI changes |
| F17 | Тёмная/светлая/системная тема, RU/EN; `app_theme.dart`, `app_strings.dart` | SyncWatch Design + shared localization IDs | Сохранить; системная тема переключается без рестарта |
| F18 | Основные настройки: библиотека, интерфейс, звонок, подключение; `settings_screen.dart` | SettingsService + SettingsDialog | Сохранить разделы, save notice и поведение сохранения |
| F19 | Player settings: skip, preview; размер/шрифт/цвет/обводка/отступ/позиция субтитров; `player_settings_screen.dart` | SettingsService + PlayerCapabilities | Сохранить; точный runtime mapping в VLC ещё не подтверждён |
| F20 | Brightness/contrast/saturation/hue, normalize audio, smooth scaling, cursor fullscreen, preview cache 50–500 MB; `app.dart`, `player_screen.dart` | VLC adapter + renderer + preview budget | Сохранить intent; mpv interpolation/display-resample не равны простому VLC scale-флагу |
| F21 | Отдельное окно звонка, pin/minimize/resize/fullscreen, camera/mic/hangup; `call_window_view.dart`, `call_window_surface.dart` | Native CallWindowShell + Meet surface | Пользователь разрешил отдельное окно внутри приложения. Встраивание и прежние media controls ещё не доказаны |
| F22 | Call input/output preferences; camera quality 480p; `settings_screen.dart:_call` | Meet capabilities + device settings | 480p selector сейчас имеет один вариант и no-op callback; не выдавать за полноценный выбор качества |
| F23 | Пауза/диагностика при разрыве, возобновление после возврата партнёра; `library_screen.dart` | ConnectionSupervisor | Сохранить; состояние звонка не является состоянием синхронизации |
| F24 | Доступ к пользовательской папке после перезапуска, moved/stale/corrupt bookmarks; `library_access_service.dart`, `packages/syncwatch_library_access` | macOS security-scoped bookmarks | Сохранить баланс access scopes; запрет доступа не ломает загрузку настроек |
| F25 | Завершение media/call, отмена preview, очистка ресурсов; services и tests | Lifecycle owners | Сохранить; нет оставшихся camera/mic capture, child processes или файловых grants |

Файлы screens в таблице расположены в `lib/screens/`, services — в `lib/services/`, models — в `lib/models/`, core — в `lib/core/`.

## Геометрия и палитра

Источник дизайна — существующий UI, а не стандартный вид SwiftUI/WPF. Первичная библиотека описаний: `packages/design/`.

| Элемент | Значения из исходников |
|---|---|
| Dark | background `#071827`, deep `#05121E`, surface `#0C2135`, raised `#102A43`, border `#1B4060` |
| Light | background `#E7EEF4`, deep `#DCE6EE`, surface `#F1F5F8`, raised `#F7FAFC`, border `#B9C9D6` |
| Accent / success | `#2F8CFF`, soft `#6AAFFF`, success `#30D98B` |
| Library | outer padding 18, gap 14, header height 64, left column 360 |
| Settings | 680×420, sidebar 150 |
| Player settings | 680×460, sidebar 170, draggable title bar |
| Buttons / slider | filled min height 46, outlined 44, radius 12, track height 3, thumb radius 6 |
| Call window | initial prototype reference 300×210; usable Meet viewport ещё не определён |

Единицы — logical pixels прототипа; переносим как pt на Apple и DIP на Windows. Это не обещание пиксельного совпадения шрифтов на разных системах.

## Регрессии, которые нельзя потерять

В прототипе есть tests для library index/access, preview cancellation, paused state after seek, stale/foreign commands, call identity/cleanup и call window hit testing. Их сценарии переносим как acceptance vectors. Тесты LiveKit negotiation сохраняются в исходном проекте как исторический baseline; они не проверяют Google Meet.

Обе новые платформы должны пройти одну матрицу F01–F25. Неподдержанная функция отмечается явно; сохранённый переключатель с no-op действием не считается переносом функции.
