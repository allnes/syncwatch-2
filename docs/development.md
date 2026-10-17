# Development setup

The repository checks require Git and Python 3.12 or newer. They use the Python standard library and install no packages. `tools/ci/pyproject.toml` declares their runtime requirements. Editor formatting is defined by `.editorconfig`; `.gitattributes` keeps repository text in LF format.

Run from the repository root:

```sh
python3 tools/ci/check_repository.py
python3 -m unittest discover -s tools/ci/tests -v
git diff --check
```

The checks validate first-party UTF-8 text, final newlines, whitespace, Python syntax, English documentation, local links, design JSON, component token references, source submodule registrations, and the initial workflow policy. Upstream submodule content is excluded from first-party text and documentation rules. Source-pin checks inspect Git index entries and do not need dependency downloads.

CI tooling uses standard-library `unittest`. Tests create isolated temporary repositories and malformed inputs to verify meaningful failures, including broken links, invalid JSON/design values, copied vendor sources, missing Git links, unsafe workflow changes, and unsuccessful job results.

## Repository workflow

`.github/workflows/repository.yml` runs on pull requests, pushes to `main`, merge-group checks, and manual requests. It performs repository validation and CI tooling tests as independent jobs. The final `ci/required` job succeeds only when both selected jobs report `success`; missing, failed, canceled, skipped, or unknown results fail.

The workflow uses JSON-compatible YAML, allowing strict validation with the Python standard library. Use that format when editing this initial workflow. Checkout uses the hosted runner's Git and shell to fetch the exact GitHub workflow revision from this public repository. It does not depend on a remote checkout action or fetch vendor submodules. Ubuntu 24.04 supplies the initial runner environment; each job checks the Python runtime requirement.

The initial workflow policy fixes the current job set and required aggregation. Introducing additional workflows or component jobs includes a corresponding policy/test update so their actual results participate in merge checks. Native builds and physical media acceptance are added by the later CI deliverables.

Repository merge protection is a GitHub setting, separate from the workflow file. Require the actual `ci/required` status after it has run; preserve existing review and access rules when configuring it. Check a pull request's real merge eligibility and result for the selected revision rather than assuming the file alone enforces protection.

Application setup, native build commands, and provider acceptance instructions will be added with the corresponding implementations. The repository workflow does not claim that native applications or real calls have been tested.

## Pull request destination

The canonical repository is `salo-group/syncwatch`; its `main` branch is the target for product pull requests and merges. A fork can publish working branches. Check the base repository explicitly before creating or merging a pull request.

For a checkout with a fork named `origin`, configure the canonical remote and GitHub CLI default:

```sh
git remote add upstream https://github.com/salo-group/syncwatch.git
git fetch upstream
gh repo set-default salo-group/syncwatch
```

Create pull requests with `gh pr create --repo salo-group/syncwatch --base main --head <fork-owner>:<branch>`. Use the same explicit repository for review, check, protection, and merge commands. Merge only after the canonical repository's required checks pass.
