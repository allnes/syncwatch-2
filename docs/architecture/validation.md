# Validation strategy

Validation establishes the product requirements and integration gates on both supported platforms. Source checkout, document checks, unit tests, and physical media acceptance provide different evidence and must be reported separately.

## Repository checks

Run from the repository root:

```sh
git diff --check
git submodule status --recursive
python3 - <<'PYCODE'
from pathlib import Path
import json
import re

root = Path.cwd()
design = root / 'packages/design'
for path in design.rglob('*.json'):
    json.loads(path.read_text())

tokens = {}
def collect(value, path=''):
    if isinstance(value, dict) and 'value' in value:
        assert path not in tokens, path
        tokens[path] = value
    elif isinstance(value, dict):
        for key, child in value.items():
            collect(child, f'{path}.{key}' if path else key)

for path in (design / 'tokens').glob('*.json'):
    collect(json.loads(path.read_text()))
components = json.loads((design / 'components.json').read_text())['components']
for component in components.values():
    for reference in component.get('tokens', []):
        assert reference in tokens, reference

for path in [root / 'README.md', *(root / 'docs').rglob('*.md')]:
    text = path.read_text()
    assert not re.search(r'[\u0400-\u04ff]', text), path
    for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', text):
        if target.startswith(('https:', 'http:', 'mailto:', '#')):
            continue
        assert (path.parent / target.split('#')[0]).exists(), (path, target)
print('Design JSON, token references, documentation language, and local links are valid')
PYCODE
```

These checks need Python 3 and this checkout. They do not require another workspace, a device profile, or an undeclared application.

Submodules must be initialized at their recorded Git revisions with no unexplained changes. Verify that external library entries use Git link mode `160000`. A clean checkout with `git submodule update --init --recursive` must obtain the pinned sources. This source-availability check does not establish dependency closure or a successful component build.

## Executable component checks

With the first implementation of each component, add its dependency manifest, test framework, formatter/linter configuration, and exact setup/build/test commands. Cover shared contracts and platform behavior using the cases in the [implementation plan](delivery-plan.md).

Design generation must reproduce identical resources and reject invalid tokens. Domain tests must cover lifecycle, ordering, and cancellation. Bridge tests must cover malformed, partial, duplicated, stale, and oversized messages. Metadata tests must cover authorization, snapshots, room isolation, and recovery.

## Native and provider acceptance

- Validate native video rendering, overlays, input, fullscreen, tracks, settings, preview isolation, and hardware decoding on both platforms.
- Validate Google Meet account access, two-way media, controls, capture release, and declared capabilities in the chosen application-owned hosts.
- Exercise simultaneous calling and synchronized playback on two physical devices with the same identified media fixtures.
- Verify local preference persistence, filesystem grants, permissions, helper cleanup, and clean-machine packaging.
- Compare native component states against the shared design specification in dark/light themes and all supported UI languages.

Acceptance evidence belongs with the relevant implementation change or release. Include reproducible commands or steps, versions, observed behavior, and unresolved failures. Keep credentials, meeting links, private media, device configuration, raw session output, and development diaries out of the source tree.

## Release condition

Every product requirement must have a passing acceptance result or an explicitly approved scope decision. G1-G5 in the [architecture](README.md) remain open until backed by the appropriate runtime and visual evidence. Successful document validation is not runtime acceptance.
