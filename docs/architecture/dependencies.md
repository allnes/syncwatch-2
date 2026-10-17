# Внешние зависимости

Проверено 17 октября 2026 года. Gitlinks и `.gitmodules` являются источником закреплённых ревизий.

## Уже добавлены

| Submodule | Версия / commit | Назначение | Лицензия в исходниках |
|---|---|---|---|
| `3rdparty/style-dictionary` | `v5.7.0` / `745264a62d01037581c6654fb4ac66bb3d245f07` | Независимое от ОС описание дизайна и генерация платформенных ресурсов при сборке | Apache 2.0, `LICENSE`, `NOTICE` |
| `3rdparty/syncplay` | `v1.7.6` / `993232ab095bb810593459bc705b3e6fc64ad161` | Настоящий Syncplay client engine и сервер | Apache 2.0 по `LICENSE`; отдельные bundled файлы имеют свои notices |
| `3rdparty/vlc` | `3.0.24` / `6de05adcbaf2e8b85fe86aad4169393098628119` | Встраиваемый libVLC и его заголовки C API | `COPYING.LIB`: LGPL 2.1; весь VLC и отдельные модули имеют другие условия, см. `COPYING` и заголовки файлов |

Требование Apache 2.0 относится к библиотеке общего дизайна. Называть VLC библиотекой Apache 2.0 нельзя. В приложении используются собственные Swift C interop / C# P/Invoke адаптеры libVLC; VLCKit и LibVLCSharp пока не добавляются.

Style Dictionary является инструментом сборки, а не движком интерфейса. Он не требует JavaScript runtime внутри нативного интерфейса. У закреплённой версии требование Node.js `>=22.0.0` в `package.json`.

## Правило для полного дерева

Каждая внешняя библиотека, включая транзитивную, должна иметь исходники в закреплённом submodule под `3rdparty/`. Добавление только верхнего проекта не закрывает это требование для его зависимостей. Внешние библиотеки не копируются в `packages/`, `apps/` или `services/`.

Перед первым build соответствующего компонента:

1. Получить полный runtime/build dependency graph для выбранной конфигурации.
2. Для каждого компонента записать upstream URL, точную ревизию, лицензию и область использования.
3. Добавить исходники через submodule. Использовать локальные пути при сборке; registry/cache не заменяют source pin.
4. Закрепить соответствие binary artifact → source commits + build flags + toolchain + SHA-256.
5. Собирать при отключённой неявной загрузке зависимостей. Проверять licenses/notices итогового набора модулей.

SDK, компиляторы и системные фреймворки SwiftUI/AppKit/WebKit/.NET/WPF учитываются как платформа сборки. Google Meet — удалённый сервис с собственными условиями, его серверный исходный код не является зависимостью приложения.

## Ещё не материализованы: до сборки обязательны

| Компонент | Предстоящее дерево | Текущий статус |
|---|---|---|
| Syncplay headless bridge | CPython, Twisted TLS и реальные транзитивные зависимости: среди заявленных upstream — `certifi`, `pem`, платформенные extras | Требования прочитаны в `3rdparty/syncplay/requirements.txt`; версии транзитивных компонентов ещё не разрешены и submodules не добавлены |
| Генератор дизайна | Runtime dependencies закреплённого `style-dictionary/package.json`, включая зависимости зависимостей | Исходник генератора добавлен; `npm install`/`npm ci` не запускались |
| Сборка VLC | Выбранные codecs, demuxers, filters и прочие contrib | Подмножество ещё не определено; upstream contrib downloader нельзя запускать без адаптации под правило submodules |
| Meet window на Windows | Кандидат с открытыми исходниками: CEF + CefSharp + соответствующий Chromium и транзитивные исходники | Требует технического эксперимента; пока не выбран и не добавлен |

Это полный список известных групп незавершённой комплектации, а не готовый SBOM. Репозиторий на этапе архитектуры не заявляется готовым к offline build.

## Meet и закрытые SDK

WebView2 — возможная практическая альтернатива для Windows, но его закрытый runtime/SDK нельзя представить submodule с исходным кодом: samples не заменяют библиотеку. Он не выбран для поставки при текущем строгом правиле. Переход на WebView2 потребует явного решения пользователя об исключении. CEF/CefSharp дают открытые исходники, но сами по себе не решают ограничения Google sign-in и не доказывают, что Meet поддерживает такой host.

## Работа с submodules

Из корня Git checkout:

```sh
git submodule update --init --recursive
git submodule status --recursive
git diff --submodule=short
```

Обновление — отдельный законченный шаг: проверить release и лицензию, checkout точного commit, обновить эту таблицу, прогнать затронутые проверки, commit и push. Не использовать `git submodule update --remote` как часть воспроизводимой сборки.

## Первичные источники

- [Style Dictionary: исходники и Apache 2.0](https://github.com/style-dictionary/style-dictionary).
- [Syncplay: исходники и лицензия](https://github.com/Syncplay/syncplay).
- [VideoLAN: libVLC](https://www.videolan.org/vlc/libvlc.html).
- [CEF](https://github.com/chromiumembedded/cef), [CefSharp](https://github.com/cefsharp/CefSharp).
- [WebView2: варианты поставки runtime](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution).
