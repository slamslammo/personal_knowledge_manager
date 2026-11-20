"""Compare published Markdown with Feishu readback without discarding content.

Only known formatting changes are folded. Links, code and table cells remain
separate values; unsupported input requires review instead of guessing equality.
The supported subset is the current weekly format: headings, prose, unordered
lists, quotations, links, inline code and tables. Images, code blocks, ordered
lists and other unknown constructs require review. No filesystem/network I/O.
"""
from __future__ import annotations

import html
from html.parser import HTMLParser
import json
import re
from dataclasses import dataclass, field


class UnsupportedFormat(ValueError):
    pass


_TICK = chr(96)
_BLOCKS = {"html", "head", "body", "title", "p", "div", "blockquote", "ul",
           "li", "table", "thead", "tbody", "tfoot", "tr", "td", "th",
           *(f"h{i}" for i in range(1, 7))}
_INLINE = {"b", "strong", "i", "em", "u", "span", "a", "code"}
_VOID = {"br", "hr", "col"}
_ALLOWED = _BLOCKS | _INLINE | _VOID | {"colgroup"}
_HTML_START = re.compile(r"<(?:html|body|title|h[1-6]|p|div|ul|ol|table|blockquote|pre)\b", re.I)


@dataclass
class _Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        if tag not in _ALLOWED:
            raise UnsupportedFormat("unknown HTML element")
        node = _Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if len(self.stack) == 1 or self.stack[-1].tag != tag:
            raise UnsupportedFormat("unbalanced HTML")
        self.stack.pop()

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _push(tokens: list, value):
    if isinstance(value, str):
        if value:
            if tokens and isinstance(tokens[-1], str):
                tokens[-1] += value
            else:
                tokens.append(value)
    else:
        tokens.append(value)


def _compact(tokens: list) -> tuple:
    """Fold prose whitespace, keeping code and link destinations untouched."""
    result = []
    for token in tokens:
        _push(result, re.sub(r"\s+", " ", token) if isinstance(token, str) else token)
    if result and isinstance(result[0], str):
        result[0] = result[0].lstrip()
    if result and isinstance(result[-1], str):
        result[-1] = result[-1].rstrip()
    return tuple(token for token in result if token != "")


def _plain(nodes: list) -> str:
    if any(not isinstance(n, str) for n in nodes):
        raise UnsupportedFormat("nested markup in code")
    return "".join(nodes)


def _html_inline(nodes: list) -> list:
    result = []
    for node in nodes:
        if isinstance(node, str):
            _push(result, node)  # HTMLParser already decoded entities exactly once.
        elif node.tag == "a":
            if not isinstance(node.attrs.get("href"), str):
                raise UnsupportedFormat("link without destination")
            result.append(("link", _compact(_html_inline(node.children)), node.attrs["href"]))
        elif node.tag == "code":
            result.append(("code", _plain(node.children)))
        elif node.tag == "br":
            result.append(("break",))
        elif node.tag in _INLINE - {"a", "code"}:
            for token in _html_inline(node.children):
                _push(result, token)
        elif node.tag == "p":
            if result:
                _push(result, " ")
            for token in _html_inline(node.children):
                _push(result, token)
        else:
            raise UnsupportedFormat("unsupported inline element")
    return result


def _closing(text: str, start: int, left: str, right: str) -> int:
    depth = 1
    i = start
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == left:
            depth += 1
        elif text[i] == right:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise UnsupportedFormat("unclosed Markdown link")


def _markdown_inline(text: str) -> list:
    result = []
    i = 0
    while i < len(text):
        if text.startswith("<!--", i):
            end = text.find("-->", i + 4)
            if end < 0:
                raise UnsupportedFormat("unclosed comment")
            i = end + 3
            continue
        if text[i] == "\\" and i + 1 < len(text) and not text[i + 1].isalnum():
            _push(result, text[i + 1])
            i += 2
            continue
        if text[i] == _TICK:
            count = len(text[i:]) - len(text[i:].lstrip(_TICK))
            marker = _TICK * count
            end = text.find(marker, i + count)
            if end < 0:
                raise UnsupportedFormat("unclosed inline code")
            code = text[i + count:end].replace("\n", " ")
            if code.startswith(" ") and code.endswith(" ") and code.strip():
                code = code[1:-1]
            result.append(("code", code))
            i = end + count
            continue
        if text.startswith("![", i):
            raise UnsupportedFormat("images require review")
        if text[i] == "[":
            begin = i + 1
            end = _closing(text, begin, "[", "]")
            if text[end + 1:end + 2] == "(":
                url_end = _closing(text, end + 2, "(", ")")
                destination = text[end + 2:url_end]
                if destination.startswith("<") and destination.endswith(">"):
                    destination = destination[1:-1]
                if re.search(r"\s", destination):
                    raise UnsupportedFormat("link titles are not supported")
                destination = html.unescape(re.sub(r"\\([\\()])", r"\1", destination))
                label = text[begin:end]
                result.append(("link", _compact(_markdown_inline(label)), destination))
                i = url_end + 1
                continue
        if text[i] == "<":
            end = text.find(">", i + 1)
            if end >= 0 and re.match(r"https?://", text[i + 1:end]):
                url = html.unescape(text[i + 1:end])
                result.append(("link", (url,), url))
                i = end + 1
                continue
        styled = False
        for marker in ("**", "__", "*", "_"):
            if not text.startswith(marker, i):
                continue
            if marker.startswith("_") and i and text[i - 1].isalnum():
                continue
            end = text.find(marker, i + len(marker))
            inner = text[i + len(marker):end]
            if end >= 0 and inner and not inner[0].isspace() and not inner[-1].isspace():
                for token in _markdown_inline(inner):
                    _push(result, token)
                i = end + len(marker)
                styled = True
                break
        if styled:
            continue
        # Decode prose entities once, rather than unescaping a completed document.
        if text[i] == "&":
            entity = re.match(r"&(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);", text[i:])
            if entity:
                _push(result, html.unescape(entity.group()))
                i += len(entity.group())
                continue
        _push(result, text[i])
        i += 1
    return result


def _table_cells(line: str) -> list[str]:
    cells, value = [], []
    i, code = 0, ""
    while i < len(line):
        char = line[i]
        if char == "\\" and i + 1 < len(line):
            value.extend(line[i:i + 2])
            i += 2
            continue
        if char == _TICK:
            count = len(line[i:]) - len(line[i:].lstrip(_TICK))
            marker = _TICK * count
            code = "" if code == marker else marker if not code else code
            value.append(marker)
            i += count
            continue
        if char == "|" and not code:
            cells.append("".join(value).strip())
            value = []
        else:
            value.append(char)
        i += 1
    cells.append("".join(value).strip())
    if line.lstrip().startswith("|"):
        cells.pop(0)
    if line.rstrip().endswith("|") and not code:
        cells.pop()
    return cells


def _serialize(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _markdown_parts(text: str) -> tuple[str, list[str]]:
    title, body = "", []
    lines = text.replace("\r\n", "\n").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        if line.startswith((_TICK * 3, "~~~")):
            raise UnsupportedFormat("fenced code requires review")
        if i < len(lines) and "|" in line:
            separators = _table_cells(lines[i])
            if separators and all(re.fullmatch(r":?-{3,}:?", cell) for cell in separators):
                width = len(separators)
                rows = [line]
                i += 1
                while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                    rows.append(lines[i].strip())
                    i += 1
                for row in rows:
                    cells = _table_cells(row)
                    if len(cells) != width:
                        raise UnsupportedFormat("ambiguous Markdown table")
                    body.append(_serialize(("row", tuple(_compact(_markdown_inline(cell)) for cell in cells))))
                continue
        if re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", line):
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            line = heading.group(2)
        else:
            line = re.sub(r"^(?:>\s?)+", "", line)
            line = re.sub(r"^[-*+]\s+", "", line)
        if not heading and re.match(r"^\d+[.)]\s+", line):
            raise UnsupportedFormat("ordered lists require review")
        tokens = _compact(_markdown_inline(line))
        if heading and len(heading.group(1)) == 1 and not title:
            title = _serialize(tokens)
        elif tokens:
            body.append(_serialize(("line", tokens)))
    return title, body


def _html_parts(text: str) -> tuple[str, list[str]]:
    parser = _Tree()
    parser.feed(text)
    parser.close()
    if len(parser.stack) != 1:
        raise UnsupportedFormat("unclosed HTML")
    title, body = "", []

    def lines(nodes):
        tokens = []
        for token in _html_inline(nodes):
            if token == ("break",):
                append(tokens)
                tokens = []
            else:
                _push(tokens, token)
        append(tokens)

    def append(tokens):
        compact = _compact(tokens)
        if compact:
            body.append(_serialize(("line", compact)))

    def walk(node):
        nonlocal title
        if isinstance(node, str):
            if node.strip():
                lines([node])
            return
        if node.tag in {"title", "h1"} and not title:
            title = _serialize(_compact(_html_inline(node.children)))
        elif node.tag == "table":
            def rows(parent):
                for row in parent.children:
                    if isinstance(row, str):
                        if row.strip():
                            raise UnsupportedFormat("text outside table cells")
                    elif row.tag in {"thead", "tbody", "tfoot"}:
                        rows(row)
                    elif row.tag == "colgroup":
                        continue
                    elif row.tag == "tr":
                        cells = []
                        for cell in row.children:
                            if isinstance(cell, str) and not cell.strip():
                                continue
                            if isinstance(cell, str) or cell.tag not in {"td", "th"}:
                                raise UnsupportedFormat("unsupported table row")
                            if any(cell.attrs.get(a, "1") != "1" for a in ("colspan", "rowspan")):
                                raise UnsupportedFormat("merged table cells")
                            cells.append(_compact(_html_inline(cell.children)))
                        body.append(_serialize(("row", tuple(cells))))
                    else:
                        raise UnsupportedFormat("unsupported table element")
            rows(node)
        elif node.tag in {"html", "head", "body", "ul", "blockquote"} or (
                node.tag == "div" and any(isinstance(c, _Node) and c.tag in _BLOCKS for c in node.children)):
            for child in node.children:
                walk(child)
        elif node.tag in {"hr", "colgroup"}:
            pass
        elif node.tag in {"p", "div", "li", "h1", *(f"h{i}" for i in range(2, 7))}:
            lines(node.children)
        else:
            raise UnsupportedFormat("unsupported block element")

    for node in parser.root.children:
        walk(node)
    return title, body


def document_parts(text: str) -> tuple[str, list[str]]:
    """Return canonical title and ordered body records; never flatten cell boundaries."""
    if not isinstance(text, str) or not text.strip():
        raise UnsupportedFormat("empty document")
    # Feishu HTML starts at the document boundary. A literal tag in Markdown prose
    # must not cause the complete source to be interpreted as HTML.
    stripped = re.sub(r"(?s)^\s*(?:<!--.*?-->\s*)*", "", text)
    return _html_parts(text) if _HTML_START.match(stripped) else _markdown_parts(text)


def compare_documents(expected: str, actual: str) -> dict:
    """Safe shared API for acceptance and production; unknown formats require review."""
    try:
        exp_title, exp_body = document_parts(expected)
        act_title, act_body = document_parts(actual)
    except (UnsupportedFormat, TypeError, RecursionError):
        return {"content_match": "manual_review", "comparison_error": "unsupported_format",
                "title_match": False, "body_lines": "unknown", "first_diff_line": 0}
    first = next((i + 1 for i in range(max(len(exp_body), len(act_body)))
                  if i >= len(exp_body) or i >= len(act_body) or exp_body[i] != act_body[i]), 0)
    matched = exp_title == act_title and exp_body == act_body
    return {"content_match": "normalized_equal" if matched else "manual_review",
            "title_match": exp_title == act_title, "body_lines": f"{len(act_body)}/{len(exp_body)}",
            "first_diff_line": first}
