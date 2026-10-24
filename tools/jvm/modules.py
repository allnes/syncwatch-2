"""Compile reviewed Kotlin source sets without flattening multiplatform ownership."""

import os
from pathlib import Path
import re

import kotlin


def fragment_arguments(fragments, refines, allow_empty_platform=False):
    """Keep intermediate expect/actual refinements, with one JVM leaf."""
    if not fragments or any(not re.fullmatch(r"[a-z][a-z0-9-]*", name) for name in fragments):
        raise ValueError("Kotlin fragments require distinct portable names")
    parents = {name: set() for name in fragments}
    for child, parent in refines:
        if child not in parents or parent not in parents or child == parent or parent in parents[child]:
            raise ValueError("Invalid or duplicate Kotlin fragment refinement")
        parents[child].add(parent)
    order = []
    pending = set(parents)
    while pending:
        ready = sorted(name for name in pending if parents[name] <= set(order))
        if not ready:
            raise ValueError("Kotlin fragment refinements contain a cycle")
        order.extend(ready)
        pending.difference_update(ready)
    ancestors = {parent for values in parents.values() for parent in values}
    leaves = set(parents) - ancestors
    if len(leaves) != 1:
        raise ValueError("A JVM module requires exactly one platform leaf")
    leaf = next(iter(leaves))
    sources = []
    assignments = []
    seen = set()
    for name in order:
        for path in sorted(map(Path, fragments[name]), key=lambda p: p.as_posix()):
            path = path.resolve()
            if (not path.is_file() or path.suffix not in {".kt", ".java"} or any(c in str(path) for c in ",\r\n\x00")
                    or path.suffix == ".java" and name != leaf):
                raise ValueError("Fragment sources must be explicit existing Kotlin files or JVM-leaf Java files")
            if path in seen:
                raise ValueError("A source file cannot belong to multiple Kotlin fragments")
            seen.add(path)
            sources.append(str(path))
            assignments.append("-Xfragment-sources=" + name + ":" + str(path))
    if not sources or not any(n.endswith(".kt") for n in sources) or (not fragments[leaf] and not allow_empty_platform):
        raise ValueError("The JVM leaf must contain reviewed source files")
    return ["-Xmulti-platform", "-Xexpect-actual-classes", "-Xfragments=" + ",".join(order),
            *["-Xfragment-refines=" + child + ":" + parent for child in order for parent in sorted(parents[child])],
            *assignments], sources


def compile_module(fragments, refines, classpath, output, directory, jdk_home, compiler_home, arguments,
                   allow_empty_platform=False, plugins=()):
    hierarchy, sources = fragment_arguments(fragments, refines, allow_empty_platform)
    if any(str(a).startswith(("-Xfragment", "-Xcommon-sources", "-Xmulti-platform")) for a in arguments):
        raise ValueError("Compiler options cannot replace the reviewed source hierarchy")
    return kotlin.compile([*arguments, *hierarchy, "-classpath", os.pathsep.join(map(str, classpath)),
                           "-d", str(output), *sources], directory, jdk_home, compiler_home, plugins=plugins)
