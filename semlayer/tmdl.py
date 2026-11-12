"""A reader for the TMDL this repo writes.

TMDL is indentation-based: each object line (`table X`, `measure Y = ...`)
opens a block; its properties sit one tab deeper (`formatString: 0.0`, or a
bare flag like `isHidden`); a multi-line expression after `=` sits two tabs
deeper than the line that opened it. `///` lines describe the object that
follows. That is all the rules in semlayer.rules need, so that is all this
reads. It is not a full TMDL implementation; Tabular Editor and the Fabric
service remain the authority on what is valid.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

OBJECT_KEYWORDS = {
    "database",
    "model",
    "table",
    "column",
    "measure",
    "partition",
    "hierarchy",
    "level",
    "relationship",
    "role",
    "tablePermission",
    "calculationGroup",
    "calculationItem",
    "expression",
    "refreshPolicy",
    "annotation",
    "culture",
    "perspective",
    "ref",
    "variation",
    "member",
    "dataAccessOptions",
    "queryGroup",
}
NAME = r"'(?:[^']|'')*'|[^\s=']+"
OBJECT_LINE = re.compile(rf"^(?P<kw>\w+)(?:\s+(?P<name>{NAME}))?(?:\s*=\s*(?P<expr>.*))?$")
PROPERTY_LINE = re.compile(r"^(?P<key>\w+):\s*(?P<value>.*)$")
EXPR_PROPERTY_LINE = re.compile(r"^(?P<key>\w+)\s*=\s*(?P<expr>.*)$")


def unquote(name: str | None) -> str | None:
    if name and name.startswith("'") and name.endswith("'"):
        return name[1:-1].replace("''", "'")
    return name


@dataclass
class Node:
    kind: str
    name: str | None = None
    expression: str | None = None
    props: dict[str, str] = field(default_factory=dict)
    flags: set[str] = field(default_factory=set)
    children: list[Node] = field(default_factory=list)
    description: str | None = None
    file: str = ""
    line: int = 0

    def all(self, kind: str) -> list[Node]:
        return [c for c in self.children if c.kind == kind]

    def first(self, kind: str) -> Node | None:
        found = self.all(kind)
        return found[0] if found else None

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    @property
    def where(self) -> str:
        return f"{self.file}:{self.line}"


def _depth(raw: str) -> int:
    return len(raw) - len(raw.lstrip("\t"))


def parse_text(text: str, file: str = "") -> list[Node]:
    lines = text.splitlines()
    roots: list[Node] = []
    stack: list[tuple[int, Node]] = []
    pending_desc: list[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue
        d = _depth(raw)
        if stripped.startswith("///"):
            pending_desc.append(stripped[3:].strip())
            i += 1
            continue
        while stack and stack[-1][0] >= d:
            stack.pop()
        parent = stack[-1][1] if stack else None

        def take_block(start: int, base: int) -> tuple[str, int]:
            """Lines at least two tabs deeper than base form the expression."""
            body, j = [], start
            while j < len(lines):
                nxt = lines[j]
                if nxt.strip() and _depth(nxt) < base + 2:
                    break
                body.append(nxt[base + 2 :] if nxt.strip() else "")
                j += 1
            while body and not body[-1].strip():
                body.pop()
            return "\n".join(body), j

        m_prop = PROPERTY_LINE.match(stripped)
        m_obj = OBJECT_LINE.match(stripped)
        m_expr = EXPR_PROPERTY_LINE.match(stripped)
        kw = stripped.split()[0]
        if kw == "ref":
            parts = stripped.split(None, 2)
            node = Node(
                kind="ref",
                name=unquote(parts[2]) if len(parts) > 2 else None,
                props={"refKind": parts[1]},
                file=file,
                line=i + 1,
            )
            pending_desc = []
            (parent.children if parent else roots).append(node)
            stack.append((d, node))
            i += 1
            continue
        if kw in OBJECT_KEYWORDS and m_obj:
            node = Node(
                kind=m_obj["kw"],
                name=unquote(m_obj["name"]),
                file=file,
                line=i + 1,
                description=" ".join(pending_desc) or None,
            )
            pending_desc = []
            expr = m_obj["expr"]
            i += 1
            if expr is not None and expr.strip() == "":
                expr, i = take_block(i, d)
            node.expression = expr
            (parent.children if parent else roots).append(node)
            stack.append((d, node))
            continue
        if parent is None:
            raise ValueError(f"{file}:{i + 1}: property outside an object: {stripped}")
        if m_prop and not m_expr:
            parent.props[m_prop["key"]] = m_prop["value"].strip()
            i += 1
        elif m_expr:
            expr = m_expr["expr"]
            i += 1
            if expr.strip() == "":
                expr, i = take_block(i, d)
            parent.props[m_expr["key"]] = expr
        elif re.fullmatch(r"\w+", stripped):
            parent.flags.add(stripped)
            i += 1
        else:
            raise ValueError(f"{file}:{i + 1}: cannot read line: {stripped}")
    return roots


@dataclass
class Model:
    root: Path
    nodes: list[Node]

    @property
    def model(self) -> Node:
        return next(n for n in self.nodes if n.kind == "model")

    @property
    def database(self) -> Node | None:
        return next((n for n in self.nodes if n.kind == "database"), None)

    @property
    def tables(self) -> list[Node]:
        return [n for n in self.nodes if n.kind == "table"]

    def table(self, name: str) -> Node:
        return next(t for t in self.tables if t.name == name)

    @property
    def relationships(self) -> list[Node]:
        return [n for n in self.nodes if n.kind == "relationship"]

    @property
    def roles(self) -> list[Node]:
        return [n for n in self.nodes if n.kind == "role"]

    @property
    def expressions(self) -> list[Node]:
        return [n for n in self.nodes if n.kind == "expression"]

    def measures(self) -> list[tuple[Node, Node]]:
        return [(t, m) for t in self.tables for m in t.all("measure")]


def load(definition_dir: Path) -> Model:
    nodes: list[Node] = []
    for path in sorted(definition_dir.rglob("*.tmdl")):
        nodes.extend(parse_text(path.read_text(), str(path.relative_to(definition_dir))))
    return Model(definition_dir, nodes)
