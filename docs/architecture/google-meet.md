# Google Meet в отдельном окне приложения

Требование после уточнения пользователя: звонок может жить в отдельном окне, но внутри приложения. Собственное owned window с Meet surface является целью. Внешнее окно обычного браузера не объявляется выполнением этого требования.

Статус: проект интеграции, техническая осуществимость на обеих ОС не доказана. Доступность web page не равна поддержке Google Meet, а наличие исходников browser host не решает Google authentication.

## Что подтверждено официальными источниками

| Возможность | Что из неё следует для проекта |
|---|---|
| Meet REST API создаёт/управляет spaces и предоставляет данные conferences | Можно отдельно спроектировать создание ссылки через API; это не библиотека двустороннего звонка. [REST overview](https://developers.google.com/workspace/meet/api/guides/overview) |
| `spaces.create` создаёт meeting space | Это optional convenience после OAuth setup. В первой версии разрешён ввод существующего Meet URL. [Method reference](https://developers.google.com/workspace/meet/api/reference/rest/v2/spaces/create) |
| Meet Media API даёт получение media и participant metadata; новые регистрации закрыты | Не назначаем её обязательным двусторонним SDK и не предполагаем доступ к программе. [Media API](https://developers.google.com/workspace/meet/media-api/guides/overview) |
| Meet add-ons размещают приложение в интерфейсе Meet | Это обратное направление встраивания и не доказательство возможности вставить Meet в native app. [Add-ons overview](https://developers.google.com/workspace/meet/add-ons/guides/overview) |
| Поддерживаются Chrome, Firefox, Edge и Safari | WKWebView, CEF и WebView2 нельзя автоматически считать поддерживаемыми продуктами Meet. [Requirements](https://support.google.com/meet/answer/7317473?hl=en) |
| Google ограничивает OAuth в embedded user agents | Для API authorization нужен системный external-user-agent flow. Полученный API token не создаёт автоматически web login session Meet внутри app browser. [Google OAuth native apps](https://developers.google.com/identity/protocols/oauth2/native-app), [embedded webviews policy](https://developers.googleblog.com/upcoming-security-changes-to-googles-oauth-20-authorization-endpoint-in-embedded-webviews/) |

Вывод из этих источников: публично документированные интерфейсы не дают нам подтверждённого замещения LiveKit с прежними native camera/mic/speaking callbacks. Это вывод архитектуры, а не утверждение Google о невозможности любого стороннего host.

## Proposed CallWindowShell

На macOS — Swift/AppKit owned `NSWindow`, кандидат поверхности — WKWebView с top-level navigation. На Windows — C# WPF owned window; при строгом правиле открытых source submodules кандидат — CEF/CefSharp, не выбран до spike. Условия WebView2 и возможное исключение описаны в [dependencies](dependencies.md).

Приложение управляет рамкой окна: показать, скрыть, вернуть, pin, resize, minimize/fullscreen, user-visible status и error surface. Тело окна показывает настоящий Google Meet UI. Не использовать iframe, подмену User-Agent для обхода ограничения, импорт cookies чужого браузера или DOM scraping как обязательный production control API.

Meet web code получает только web permissions, необходимые звонку. Native bridge для доступа к файлам, player или room token не публикуется в provider page. Переходы на сторонние origins не получают привилегий приложения. Ошибка Google sign-in показывается пользователю; отдельный OAuth API login не выдаётся за готовое решение web login.

## Состояния и capabilities

`idle → opening → webSurfaceReady → userActionRequired → closed/failed` описывает то, что host действительно может наблюдать. Состояние `inCall`, camera/mic state, remote video availability и speaking можно показывать только при достоверном provider event. Нельзя выводить «звонок активен» только из факта успешной навигации.

| Функция прототипа | Статус для Meet |
|---|---|
| Open / restore call window | Реализуется native shell, независимо от успешного join |
| Двусторонние camera/mic и выбор устройств | Обязательны через сам Meet UI после доказанного join; управление прежними native кнопками не подтверждено |
| Hangup | Предпочтительно реальное действие пользователя в Meet UI; close window должен отдельно подтвердить прекращение capture, не просто hide |
| Remote video в произвольной области нашего окна | Provider web surface может показать видео; исходные native VideoTrack недоступны через REST |
| Отдельная call volume | Открытый вопрос. Не подменять изменением system volume или громкости всех browser windows |
| Speaking event и автоматический movie ducking | Открытый вопрос; public REST не выдаёт такой realtime callback |
| Контроль camera quality 480p | Не обещан; применяются реальные настройки Meet и ограничения host |
| Compact window 300×210 и исходный chrome | Размер — reference прототипа; usability Meet и минимальный viewport нужно проверить, изменения требуют отдельного design decision |

Capabilities (`canObserveJoin`, `canMuteFromNativeUI`, `canSelectDevicesFromNativeUI`, `canSetCallVolume`, `canObserveRemoteSpeaking`, `canConfirmHangup`) по умолчанию false и становятся true только после подтверждённого пути интеграции. В сохранении F13/F14/F21/F22 пока есть явные gaps. Не оставлять работающие на вид кнопки с no-op callback.

## Обязательный feasibility gate G1

На локальном Mac и `win-dev`, в интерактивных пользовательских сессиях:

1. Открыть отдельное app-owned окно с нормальной Meet страницей и без iframe.
2. Проверить поддержанный способ входа для реально используемого account type; отдельно проверить guest admission. Guest-only успех не закрывает signed-in сценарий.
3. Получить осознанные camera/mic permissions и установить двухсторонний звонок, включая device changes и возврат после минимизации.
4. Проверить каждый требуемый native control/capability. Зафиксировать точные gaps, не заменять их скриптами по нестабильному DOM.
5. Проверить close/hangup, отсутствие скрытого capture, reconnect, expired/revoked meeting и denied permissions.
6. Одновременно воспроизвести локальный фильм через VLC и Syncplay между Mac и Windows, проверить слышимость и отсутствие изменения громкости других приложений.

Результат gate содержит host versions, account type, наблюдения и исключает meeting URL, cookies, tokens и лица участников из опубликованных logs/screenshots. Только после этого фиксируется browser dependency graph и окончательное решение.

Если in-app host или обязательные capabilities не работают, перенос звонка считается незакрытым. Пользователю предъявляется конкретный результат и выбор изменяемого требования: внешний поддержанный браузер, другой provider или ограниченный набор функций. Сейчас ни один такой отход от требования не выбран.
