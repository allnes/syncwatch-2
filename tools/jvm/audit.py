"""Inspect a fixed JVM runtime metadata graph without downloading libraries."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import xml.etree.ElementTree as ET


class AuditError(ValueError):
    """Metadata cannot establish the declared runtime graph."""


def require(condition, message):
    if not condition:
        raise AuditError(message)


def load_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise AuditError(f"Non-finite JSON number: {value}")

    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid)


def version(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)*(?:-[A-Za-z]+[0-9.]*)?", value),
            f"Unsupported or non-fixed version: {value}")
    require("SNAPSHOT" not in value.upper(), "Snapshot versions are not fixed")
    return value


def coordinate(value):
    require(isinstance(value, str), "Coordinate must be a string")
    parts = value.split(":")
    require(len(parts) == 3 and all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", p) for p in parts[:2]),
            f"Invalid module coordinate: {value}")
    version(parts[2])
    return ":".join(parts[:2]), parts[2]


def version_constraint(constraint):
    require(isinstance(constraint, dict) and set(constraint) <= {"requires", "strictly", "prefers"},
            f"Unsupported version constraint: {constraint}")
    for kind, requested in constraint.items():
        version(requested) if kind == "prefers" else bound(kind, requested)


def bound(kind, requested):
    if isinstance(requested, str) and requested.startswith("[") and requested.endswith("]") and "," not in requested:
        return "strictly", version(requested[1:-1])
    return kind, version(requested)


def satisfies(selected, constraint):
    version_constraint(constraint)
    for kind, requested in constraint.items():
        if kind == "prefers":
            continue
        kind, requested = bound(kind, requested)
        if selected == requested:
            continue
        require(kind != "strictly", f"Strict version conflict: {selected} != {requested}")
        require("-" not in selected and ("-" not in requested or re.fullmatch(r"[0-9.]+-(?:alpha|beta|rc)[0-9]+", requested, re.I)),
                f"Prerelease version conflict requires review: {selected}, {requested}")
        left = [int(p) for p in selected.split(".")]
        right = [int(p) for p in requested.split("-", 1)[0].split(".")]
        width = max(len(left), len(right))
        require(left + [0] * (width - len(left)) >= right + [0] * (width - len(right)),
                f"Selected version {selected} is below required {requested}")


def edge(item):
    require(isinstance(item, dict) and set(item) <= {"group", "module", "version", "reason", "excludes", "endorseStrictVersions", "attributes"},
            "Unsupported dependency attributes, capabilities or substitution")
    attributes = item.get("attributes", {})
    require(attributes in ({}, {"org.gradle.category": "platform"}), "Unsupported dependency attributes")
    category = "platform" if attributes else "library"
    require(not item.get("excludes"), "Dependency exclusions require separate review")
    require(type(item.get("endorseStrictVersions", False)) is bool
            and (not item.get("endorseStrictVersions") or category == "platform"), "Unsupported strict endorsement")
    require(isinstance(item.get("group"), str) and isinstance(item.get("module"), str), "Missing dependency identity")
    key = item["group"] + ":" + item["module"]
    coordinate(key + ":0")
    constraint = item.get("version", {})
    version_constraint(constraint)
    return key, constraint, category


def gradle(data, identity, category="library"):
    require(isinstance(data, dict) and data.get("formatVersion") == "1.1", "Unsupported Gradle module format")
    c = data.get("component", {})
    owner = ":".join(str(c.get(k, "")) for k in ("group", "module", "version"))
    coordinate(owner)
    require(owner == identity or bool(c.get("url")), f"Metadata identity mismatch: {identity}")
    variants = []
    allowed = {"org.gradle.category", "org.gradle.usage", "org.gradle.libraryelements",
               "org.gradle.jvm.environment", "org.gradle.jvm.version", "org.jetbrains.kotlin.platform.type",
               "org.gradle.dependency.bundling"}
    for v in data.get("variants", []):
        require(isinstance(v, dict), "Invalid Gradle variant")
        a = v.get("attributes", {})
        if (a.get("org.gradle.usage") == "java-runtime"
                and a.get("org.jetbrains.kotlin.platform.type") in (None, "jvm")
                and a.get("org.gradle.category", "library") == ("regular-platform" if category == "platform" else "library")
                and a.get("org.gradle.libraryelements", "jar") == "jar"
                and a.get("org.gradle.jvm.environment", "standard-jvm") == "standard-jvm"):
            require(set(a) <= allowed, f"Unsupported JVM variant attributes: {identity}")
            require(a.get("org.gradle.dependency.bundling", "external") == "external", "Embedded JVM bundles require review")
            variants.append(v)
    require(len(variants) == 1, f"Expected one unambiguous JVM runtime variant: {identity}")
    v = variants[0]
    require(set(v) <= {"name", "attributes", "dependencies", "dependencyConstraints", "files", "available-at", "capabilities"},
            f"Unsupported JVM variant fields: {identity}")
    require(not v.get("capabilities"), f"Variant capabilities require separate review: {identity}")
    require(all(isinstance(v.get(k, []), list) for k in ("dependencies", "dependencyConstraints")),
            "Invalid Gradle dependency lists")
    dependencies = [edge(d) for d in v.get("dependencies", [])]
    constraints = [edge(d) for d in v.get("dependencyConstraints", [])]
    require(all(kind == "library" for _, _, kind in constraints), "Categorized version constraints require review")
    redirect = v.get("available-at")
    if redirect is not None:
        require(not dependencies and not constraints and not v.get("files"), "Redirect variant also declares content")
        redirect = ":".join(str(redirect.get(k, "")) for k in ("group", "module", "version"))
        coordinate(redirect)
    return v["name"], dependencies, constraints, redirect, owner if owner != identity else None


def pom(data, identity, category="library"):
    require(b"<!DOCTYPE" not in data.upper() and b"<!ENTITY" not in data.upper(), "POM entities are unsupported")
    root = ET.fromstring(data)
    namespace = "{http://maven.apache.org/POM/4.0.0}"
    require(root.tag == namespace + "project", "Unsupported POM root/namespace")

    def text(node, name, default=""):
        return (node.findtext(namespace + name, default) or "").strip()

    require(root.find(namespace + "parent") is None and (category == "platform" or root.find(namespace + "dependencyManagement") is None)
            and root.find(namespace + "profiles") is None, "POM inheritance, profiles and dependency management require review")
    require(":".join(text(root, k) for k in ("groupId", "artifactId", "version")) == identity,
            f"Metadata identity mismatch: {identity}")
    require(text(root, "packaging", "jar") in {"jar", "pom"}, "Unsupported JVM packaging")
    dependencies, constraints = [], []
    entries = [(d, dependencies) for d in root.findall(namespace + "dependencies/" + namespace + "dependency")]
    if category == "platform":
        entries.extend((d, constraints) for d in root.findall(namespace + "dependencyManagement/" + namespace + "dependencies/" + namespace + "dependency"))
    for d, destination in entries:
        scope, optional = text(d, "scope", "compile"), text(d, "optional", "false")
        require(scope in {"compile", "runtime", "provided", "test", "system"} and optional in {"true", "false"},
                "Unsupported POM dependency scope")
        require(destination is dependencies or (scope in {"compile", "runtime"} and optional == "false"),
                "Non-runtime or optional platform constraints require review")
        if scope in {"provided", "test"} or optional == "true":
            continue
        require(scope != "system", "System-scoped runtime dependencies require review")
        require(d.find(namespace + "exclusions") is None and not text(d, "classifier")
                and text(d, "type", "jar") == "jar", "POM exclusions/classifiers/types require review")
        destination.append(edge({"group": text(d, "groupId"), "module": text(d, "artifactId"),
                                 "version": {"requires": text(d, "version")}}))
    return "maven-platform" if category == "platform" else "maven-runtime", dependencies, constraints, None, None


def audit(inventory_path):
    inventory_path = Path(inventory_path).resolve()
    inventory = load_json(inventory_path.read_bytes())
    require(isinstance(inventory, dict) and set(inventory) == {"schemaVersion", "roots", "selections", "metadata"}
            and type(inventory["schemaVersion"]) is int and inventory["schemaVersion"] == 1, "Unsupported inventory schema")
    roots, selections, metadata = (inventory[k] for k in ("roots", "selections", "metadata"))
    require(isinstance(roots, list) and roots and len(roots) == len(set(roots)), "Roots must be nonempty and unique")
    require(isinstance(selections, dict) and isinstance(metadata, dict), "Missing explicit versions or metadata")
    for key, value in selections.items():
        coordinate(key + ":" + value)
    for identity, source in metadata.items():
        key, fixed = coordinate(identity)
        require(selections.get(key) == fixed, f"Metadata is not an explicit selected version: {identity}")
        require(isinstance(source, dict) and set(source) == {"path", "sha256", "format"}
                and source["format"] in {"gradle", "pom"}, "Invalid metadata inventory entry")
        p = PurePosixPath(source["path"])
        require(str(p) == source["path"] and not p.is_absolute() and ".." not in p.parts and "\\" not in str(p),
                "Metadata path must stay inside the inventory directory")
        require(re.fullmatch(r"[0-9a-f]{64}", source["sha256"]), "Metadata SHA-256 is required")
    nodes, constraints, owners, categories = {}, [], {}, {}

    def resolve(key, constraint):
        require(key in selections, f"Missing explicit version selection: {key}")
        satisfies(selections[key], constraint)
        return key + ":" + selections[key]

    def visit(identity, redirects=(), category="library"):
        require(identity not in redirects, f"Cyclic metadata redirect: {identity}")
        require(categories.setdefault(identity, category) == category, f"Conflicting dependency categories: {identity}")
        if identity in nodes:
            return
        require(identity in metadata, f"Missing metadata: {identity}")
        source = metadata[identity]
        path = (inventory_path.parent / source["path"]).resolve()
        require(path.is_relative_to(inventory_path.parent), "Metadata symlink leaves inventory directory")
        data = path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == source["sha256"], f"Metadata digest mismatch: {identity}")
        variant, deps, limits, redirect, owner = (gradle(load_json(data), identity, category) if source["format"] == "gradle" else pom(data, identity, category))
        selected = sorted({(resolve(k, c), kind) for k, c, kind in deps})
        node = {"coordinate": identity, "metadataSha256": source["sha256"], "format": source["format"],
                "variant": variant, "category": category, "dependencies": [c for c, _ in selected],
                "requests": sorted(({"module": k, "version": c, "category": kind} for k, c, kind in deps),
                                   key=lambda c: (c["module"], c["category"], json.dumps(c["version"], sort_keys=True))),
                "constraints": sorted(({"module": k, "version": c} for k, c, _ in limits), key=lambda c: c["module"])}
        nodes[identity] = node
        constraints.extend(limits)
        if owner:
            key, fixed = coordinate(owner)
            require(selections.get(key) == fixed, f"Missing explicit metadata owner: {owner}")
            node["owner"] = owner
            owners[identity] = owner
            visit(owner, category=category)
        if redirect:
            key, fixed = coordinate(redirect)
            require(selections.get(key) == fixed, f"Redirect version differs from explicit selection: {redirect}")
            node["redirect"] = redirect
            visit(redirect, (*redirects, identity), category)
        for dependency, kind in selected:
            visit(dependency, category=kind)

    for identity in roots:
        key, fixed = coordinate(identity)
        require(selections.get(key) == fixed, f"Root differs from explicit selection: {identity}")
        visit(identity)
    reached = {coordinate(c)[0] for c in nodes}
    for key, constraint, _ in constraints:
        if key in reached:
            satisfies(selections[key], constraint)
    for identity, owner in owners.items():
        require(nodes[owner].get("redirect") == identity, f"Metadata owner does not redirect to {identity}")
    require(set(metadata) == set(nodes), "Inventory contains unreachable metadata")
    require(set(selections) == reached, "Inventory contains unused version selections")
    return {"schemaVersion": 1, "scope": "published-jvm-runtime-metadata",
            "roots": sorted(roots), "nodes": [nodes[k] for k in sorted(nodes)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.inventory)
    except (AuditError, ValueError, OSError, KeyError, TypeError, ET.ParseError) as error:
        print(f"JVM metadata audit failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
