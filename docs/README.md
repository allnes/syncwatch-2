# Документация SyncWatch

Единая локальная точка входа: `/Users/anesterov/repos/salo-syncwatch/docs`.
В workspace это ссылка на `syncwatch/docs`, поэтому документы сохраняются в Git вместе с проектом.

## Исходные требования

- Сохранить внешний вид и функции прототипа `/Users/anesterov/repos/syncwatch-opt/syncwatch`.
- Apple: Swift. Windows: C#.
- Плеер: VLC/libVLC. Синхронизация: Syncplay. Звонки: Google Meet.
- Дизайн: отдельная библиотека с лицензией Apache 2.0.
- Все внешние зависимости: закреплённые Git submodules в `3rdparty/`.
- Каждый законченный осмысленный шаг: отдельный commit и push.

## Состояние

Архитектура подготовлена 17 октября 2026 года. Исходный прототип не изменён.

## Документы

- [Архитектура приложения](architecture/README.md): схема, модули, источники состояния, native hosts и открытые gates.
- [Матрица сохранения функций](architecture/prototype-baseline.md): 25 групп функций и точная исходная ревизия.
- [Общий дизайн](architecture/design-system.md): независимая от ОС библиотека описаний, Apache 2.0 и native renderers.
- [Syncplay и данные комнаты](architecture/syncplay.md): reuse engine, IPC, catalog exchange, reconnect и session generations.
- [Google Meet](architecture/google-meet.md): отдельное окно приложения, API limits и эксперимент встраивания.
- [Зависимости](architecture/dependencies.md): три закреплённых submodules и оставшийся transitive graph.
- [План реализации](architecture/delivery-plan.md): этапы, checks и физическая Mac/Windows приёмка.
- [Фактические проверки](architecture/verification.md): подтверждённые результаты и граница validation.

Новые приложения пока не реализованы. Meet inside-app, native VLC parity и полный source dependency graph требуют проверок, перечисленных в архитектуре. Эти gaps не заменены молча урезанием функционала.
