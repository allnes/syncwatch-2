# Inspecting JVM dependency metadata

`tools/jvm/audit.py` inspects published JVM runtime dependencies before library source adoption. It uses Python 3.12 or newer with no installed packages. It reads an explicit inventory of local Gradle Module Metadata or Maven POM files and emits a deterministic JSON graph on standard output. It does not access the network, install packages, run Gradle, compile code or select versions automatically.

This inspection covers published JVM runtime metadata. It does not establish complete source, build-tool, native-library, embedded-code, font or packaged Java runtime inventories, binary/source correspondence, API compatibility or license clearance. In particular, a Skiko runtime metadata entry does not enumerate its compiled Skia dependencies. The Linux Compose component remains unavailable in the [component registry](../tools/dependencies/components.json) until its full source/build/license graph is resolved under the [dependency policy](architecture/dependencies.md).

The [desktop UI JVM profile](compose-ui-jvm.md) owns the sixteen UI/Skiko JVM modules and compiles the actual application/design consumer. Its bytecode qualification is independent of the native renderer and application gate.

## Input inventory

Keep fetched metadata, provenance and reports in a separate audit directory. Prefer upstream Gradle `.module` metadata when published; a POM can omit multiplatform variants and rich version information. Verify the repository URL and exact coordinate for every snapshot before recording its digest. Library binaries and caches do not replace pinned source submodules.

An inventory has exactly four top-level fields:

```json
{
  "schemaVersion": 1,
  "roots": ["example:library:1.0"],
  "selections": {
    "example:library": "1.0"
  },
  "metadata": {
    "example:library:1.0": {
      "path": "library-1.0.module",
      "format": "gradle",
      "sha256": "<SHA-256 of the unmodified metadata bytes>"
    }
  }
}
```

Replace the illustrative digest with the actual 64-character lowercase SHA-256. `format` is `gradle` or `pom`. Paths are relative to the inventory file's directory; traversal and symlinks that leave it are rejected. Every reached module needs one explicit fixed version and one metadata record. Roots must match those selections. Unreachable metadata and unused selections are errors.

The caller makes and reviews version choices. A `requires` lower bound cannot exceed the explicit selection; `strictly` and Maven singleton ranges such as `[1.0]` must match exactly. A `prefers` entry is retained but does not override an explicit selection. Versionless dependencies still require that explicit selection, and all reached constraints are checked afterward. Stable selected versions may satisfy alpha/beta/RC lower bounds with the same or an earlier numeric version. Other prerelease conflicts, open ranges, dynamic versions and snapshots fail for review.

## Runtime variants and constraints

The inspector requires one unambiguous `java-runtime` variant for a standard JVM library. It excludes Android, other Kotlin targets, API-only variants and source/documentation variants. It follows `available-at` platform redirects. Platform metadata that identifies a different owning component must have a matching reverse redirect in that owner's metadata.

Explicit platform dependencies use `regular-platform` runtime variants, or a simple POM's dependency-management constraints. Strict constraints are enforced, including those supplied by an endorsed platform. Constraints apply only to modules reached by real dependency or metadata-owner edges; they do not introduce unrelated libraries.

For simple POMs, compile and runtime dependencies are included. Test, provided and optional transitive dependencies are excluded. Parent inheritance, profiles, property-based dependency versions, imported BOMs, system paths, classifiers and exclusions require separate review. Unsupported dependency/variant attributes, capability selection, embedded JVM bundles and ambiguous variants also fail. This tool intentionally supports a bounded metadata profile and does not implement Gradle's full resolution or Maven's effective-model semantics.

## Run and verify

Set `JVM_AUDIT_DIR` to the separate audit directory containing the reviewed inventory and snapshots:

```sh
python3 tools/jvm/audit.py "$JVM_AUDIT_DIR/inventory.json" > "$JVM_AUDIT_DIR/runtime-graph.json"
python3 -m unittest discover -s tools/jvm/tests -v
```

Success emits sorted coordinates, variants, metadata digests, runtime edges, platform categories, constraints and ownership links without timestamps or local paths. Failure returns a nonzero status and an error on standard error, with no success report. Use the exit status before consuming redirected output.

The regression suite is part of required repository CI. The tool and its tests are first-party Apache-2.0 code. Raw upstream metadata retains its upstream terms and stays separate from the application source.

## Format references

- [Gradle Module Metadata](https://docs.gradle.org/current/userguide/module_metadata.html).
- [Maven dependencies and version requirements](https://maven.apache.org/pom.html#dependencies).
