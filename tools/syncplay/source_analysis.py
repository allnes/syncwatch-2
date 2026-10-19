"""Inspect pinned Python sources without importing or executing the engine."""

import ast


class ImportSites(ast.NodeVisitor):
    def __init__(self, path):
        self.path = path
        self.scope = []
        self.sites = []

    def visit_ClassDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node):
        for alias in node.names:
            self.record(node, alias.name, [], 0)

    def visit_ImportFrom(self, node):
        self.record(node, node.module or "", [a.name for a in node.names], node.level)

    def record(self, node, module, names, level):
        self.sites.append({"file": self.path, "line": node.lineno, "scope": ".".join(self.scope),
                           "module": module, "names": names, "level": level})


def module_name(path):
    return path.removesuffix(".py").replace("/", ".").removesuffix(".__init__")


def imports(path, tree):
    visitor = ImportSites(path)
    visitor.visit(tree)
    package = module_name(path) if path.endswith("/__init__.py") else module_name(path).rsplit(".", 1)[0]
    for site in visitor.sites:
        if site["level"]:
            pieces = package.split(".")
            if site["level"] > len(pieces):
                raise ValueError("Relative import leaves the selected package")
            parent = pieces[:len(pieces) - site["level"] + 1]
            site["absolute"] = ".".join(parent + ([site["module"]] if site["module"] else []))
        else:
            site["absolute"] = site["module"]
    return visitor.sites


def analyze(files, standard_library):
    trees = {name: ast.parse(data, filename=name, feature_version=(3, 12))
             for name, data in sorted(files.items()) if name.endswith(".py")}
    sites = []
    signatures = {}
    config_keys = set()
    modules = {module_name(n) for n in trees if n.startswith("syncplay/")}
    for name, tree in trees.items():
        for site in imports(name, tree):
            absolute = site["absolute"]
            root = absolute.split(".")[0]
            if root == "syncplay":
                category = "selected-source" if absolute in modules else "unshipped-internal"
            elif root in standard_library:
                category = "standard-library"
            else:
                category = "unresolved-third-party"
            role = "engine-source" if name.startswith("syncplay/") else "build-reference"
            sites.append(site | {"category": category, "sourceRole": role})
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in {"SyncplayClient", "BasePlayer", "UiManager"}:
                signatures[node.name] = {f.name: ast.unparse(f.args) for f in node.body
                                         if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                target = node.value
                if ((isinstance(target, ast.Name) and target.id == "config")
                        or (isinstance(target, ast.Attribute) and target.attr == "_config")):
                    config_keys.add(node.slice.value)
    return {"schemaVersion": 1, "runtimeReady": False, "staticAnalysisOnly": True,
            "modules": sorted(modules), "imports": sites, "signatures": signatures,
            "literalConfigSubscripts": sorted(config_keys),
            "unresolvedThirdPartyRoots": sorted({s["absolute"].split(".")[0] for s in sites
                                                 if s["category"] == "unresolved-third-party" and s["sourceRole"] == "engine-source"}),
            "unresolvedBuildRoots": sorted({s["absolute"].split(".")[0] for s in sites
                                            if s["category"] == "unresolved-third-party" and s["sourceRole"] == "build-reference"}),
            "unshippedInternalModules": sorted({s["absolute"] for s in sites
                                                if s["category"] == "unshipped-internal"})}
