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

## Проверка сохранённых артефактов — выполнено

| Проверка | Результат |
|---|---|
| JSON parsing через Python stdlib | PASS: 5 JSON файлов библиотеки дизайна |
| Уникальные tokens и ссылки компонентов | PASS: 40 tokens, 18 references разрешены |
| Palette / geometry vs prototype source | PASS: 15 именованных theme constants и 21 geometry assertion; дополнительные screen colors прочитаны из исходников |
| Provenance SHA-256 | PASS: все 14 исходных файлов совпадают, prototype HEAD совпадает, исходное рабочее дерево чистое |
| Относительные Markdown links | PASS: все 17 ссылок разрешаются |
| Workspace documentation path | PASS: `docs` — symlink, разрешается в `syncwatch/docs` |
| `git submodule status --recursive` и index inspection | PASS: 3 clean submodules, все mode `160000`, ожидаемые SHA совпадают с HEAD каждого dependency |
| `git diff --check` | PASS |
| Независимое клонирование с GitHub | PASS: shallow clean clone + recursive submodule initialization получили все три точных source commits; рабочее дерево clone чистое |

Команды clean clone, фактически выполненные во временном каталоге:

```sh
git clone --depth 1 --no-recurse-submodules https://github.com/allnes/syncwatch-2.git checkout
git -C checkout submodule update --init --recursive --depth 1
git -C checkout submodule status --recursive
git -C checkout status --short
```

Clone проверял архитектурный commit `ae393fc984cb4f567e5628f4590ff057552d1a43`. Последующий commit обновляет только этот отчёт; повторная загрузка неизменённых dependency sources для него не требуется.

Компактное воспроизведение JSON/provenance проверки из корня Git checkout:

```sh
python3 - <<'PY'
from pathlib import Path
import hashlib, json, subprocess

repo = Path.cwd()
design = repo / 'packages/design'
for path in design.rglob('*.json'):
    json.loads(path.read_text())
evidence = json.loads((design / 'provenance.json').read_text())
prototype = Path('/Users/anesterov/repos/syncwatch-opt/syncwatch')
head = subprocess.check_output(['git', '-C', str(prototype), 'rev-parse', 'HEAD'], text=True).strip()
assert head == evidence['prototypeCommit']
for relative, expected in evidence['files'].items():
    assert hashlib.sha256((prototype / relative).read_bytes()).hexdigest() == expected, relative
print('JSON and prototype source hashes match')
PY
git diff --check
git submodule status --recursive
```

Проверка source hashes требует наличия неизменённого prototype checkout; clone/source inspection не являются сборкой или тестированием runtime dependencies.

## Не выполнялось

- Новая Swift/C# реализация, её build/test, генерация Swift/XAML или установка транзитивных зависимостей.
- Headless Syncplay import/init и запуск нового bridge/server/RoomMetadata.
- Новая физическая двухсторонняя media validation, VLC playback на новой архитектуре или Google Meet call.
- Полная визуальная фиксация всех экранов прототипа и comparison с native renderers.
- Установка .NET SDK, открытие RDP session, изменение Windows settings или существующего prototype deployment.

Открытое старое приложение было просмотрено, но полученный snapshot не стал полным screen baseline. Исторические результаты прототипа не выдаются за проверку новой версии.
