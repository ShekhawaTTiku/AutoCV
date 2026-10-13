"""LaTeX syntax analysis, bounded section segmentation, and safe replacement."""
from collections import Counter
from dataclasses import replace
import hashlib
import re

from src.constants import PROTECTED, SECTION_COMMANDS
from src.exceptions import EditError
from src.models import Project, Section
from src.project_io import _decode


def _mask(source: str) -> str:
    """Hide comments and verbatim blocks without changing source character offsets."""
    result, i = list(source), 0
    while i < len(source):
        end = i
        if source[i] == "%":
            end = source.find("\n", i)
            end = len(source) if end < 0 else end
        elif source[i] == "\\":
            match = re.match(r"\\([A-Za-z@]+|.)", source[i:], re.S)
            if match:
                command, after = match.group(1), i + match.end()
                if command == "verb":
                    after += int(after < len(source) and source[after] == "*")
                    if after < len(source) and not source[after].isspace():
                        end = source.find(source[after], after + 1)
                        end = len(source) if end < 0 else end + 1
                elif command == "begin":
                    env = re.match(r"\s*\{(verbatim|Verbatim|lstlisting|minted|comment)\}", source[after:])
                    if env:
                        closing = "\\end{" + env.group(1) + "}"
                        end = source.find(closing, after + env.end())
                        end = len(source) if end < 0 else end + len(closing)
                if end == i:
                    i = after  # Consume escaped percent signs and braces.
                    continue
        if end > i:
            result[i:end] = ["\n" if c == "\n" else " " for c in source[i:end]]
            i = end
        else:
            i += 1
    return "".join(result)


def _commands(source: str):
    """Yield all LaTeX command names, positions, and brace depths."""
    i, depth = 0, 0
    while i < len(source):
        if source[i] == "\\":
            match = re.match(r"\\([A-Za-z@]+|.)", source[i:], re.S)
            if match:
                end = i + match.end()
                yield match.group(1), i, end, depth
                i = end
                continue
        elif source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
        i += 1


def _group(source: str, index: int, opening: str = "{", closing: str = "}"):
    """Find and return the content and end index of a matched braced group."""
    while index < len(source) and source[index].isspace():
        index += 1
    if index >= len(source) or source[index] != opening:
        return None
    start, depth, braces, i = index + 1, 1, 0, index + 1
    while i < len(source):
        if source[i] == "\\":
            match = re.match(r"\\([A-Za-z@]+|.)", source[i:], re.S)
            i += match.end() if match else 1
            continue
        if opening == "[" and source[i] == "{":
            braces += 1
        elif opening == "[" and source[i] == "}":
            braces -= 1
        elif source[i] == opening and not braces:
            depth += 1
        elif source[i] == closing and not braces:
            depth -= 1
            if depth == 0:
                return source[start:i], i + 1
        i += 1
    return None


def sections(project: Project) -> list[Section]:
    """Parse and return all safely bounded editable sections in the project."""
    result = []
    for filename in project.tex_files:
        source = _decode(project.files[filename])
        masked = _mask(source)
        body_start, body_end, headers = 0, len(source), []
        commands = list(_commands(masked))
        for command, start, end, depth in commands:
            group = _group(masked, end) if command in {"begin", "end"} and depth == 0 else None
            if group and group[0].strip() == "document":
                if command == "begin":
                    body_start = group[1]
                else:
                    body_end = start
                    break
        for command, start, end, depth in commands:
            if command not in SECTION_COMMANDS or depth or not body_start <= start < body_end:
                continue
            rest = re.match(r"\s*\*?\s*", masked[end:])
            i = end + rest.end()
            if i < len(masked) and masked[i] == "[":
                optional = _group(masked, i, "[", "]")
                if not optional:
                    continue
                i = optional[1]
            title = _group(masked, i)
            if title:
                title_start = i + len(masked[i:]) - len(masked[i:].lstrip()) + 1
                headers.append((start, title[1], command, source[title_start:title[1] - 1].strip()))
        counts = Counter()
        for index, (start, end, command, title) in enumerate(headers):
            counts[(command, title)] += 1
            identity = f"{filename}\0{command}\0{title}\0{counts[(command, title)]}"
            stop = headers[index + 1][0] if index + 1 < len(headers) else body_end
            result.append(Section(hashlib.sha256(identity.encode()).hexdigest()[:16], title, end, stop,
                                  source[end:stop], filename))
        if (not headers and body_start == 0 and body_end == len(source)
                and source.strip() and not any(c in PROTECTED for c, *_ in commands)):
            identity = hashlib.sha256(f"{filename}\0document-body".encode()).hexdigest()[:16]
            result.append(Section(identity, "Included content", body_start, body_end,
                                  source[body_start:body_end], filename))
    return result


def _profile(source: str):
    """Compute brace balance and environment stack profile."""
    masked, depth, minimum, opening, closing = _mask(source), 0, 0, [], []
    consumed = {i for _, start, end, _ in _commands(masked) for i in range(start, end)}
    for i, char in enumerate(masked):
        if i not in consumed:
            depth += (char == "{") - (char == "}")
            minimum = min(minimum, depth)
    for command, _, end, _ in _commands(masked):
        if command not in {"begin", "end"}:
            continue
        group = _group(masked, end)
        if not group:
            raise EditError("An environment name is incomplete.")
        env = group[0].strip()
        if env == "document":
            raise EditError("A section edit cannot change document boundaries.")
        if command == "begin":
            opening.append(env)
        elif opening:
            if opening.pop() != env:
                raise EditError("The edit mismatches LaTeX environments.")
        else:
            closing.append(env)
    return depth, minimum, tuple(closing), tuple(opening)


def _protected(source: str):
    """Count protected LaTeX macro invocations to prevent unauthorized structural changes."""
    masked, fragments = [] if not source else _mask(source), []
    for command, start, end, _ in _commands(masked):
        if command not in PROTECTED:
            continue
        last, i = end, end
        while i < len(masked) and masked[i].isspace():
            i += 1
        if i < len(masked) and masked[i] == "*":
            i += 1
        while True:
            while i < len(masked) and masked[i].isspace():
                i += 1
            if i >= len(masked) or masked[i] not in "[{":
                break
            group = _group(masked, i, masked[i], "]" if masked[i] == "[" else "}")
            if not group:
                break
            last = i = group[1]
        if last == end:
            newline = masked.find("\n", end)
            last = len(masked) if newline < 0 else newline
        fragments.append(masked[start:last])
    return Counter(fragments)


def replace_section(project: Project, section_id: str, new_body: str) -> Project:
    """Validate and atomically replace a target section's body within the project."""
    selected = next((s for s in sections(project) if s.id == section_id), None)
    if selected is None:
        raise EditError("Choose a section from the current resume.")
    if not isinstance(new_body, str) or not new_body.strip() or len(new_body) > 200_000:
        raise EditError("The replacement must be a nonempty LaTeX section body.")
    if "\n" not in new_body and r"\n" in new_body:
        new_body = new_body.replace(r"\r\n", "\n").replace(r"\n", "\n")
    new_body = re.sub(r"\\\\([A-Za-z@]+)", r"\\\1", new_body)
    old_bytes = project.files[selected.file]
    newline = "\r\n" if b"\r\n" in old_bytes else "\n"
    new_body = new_body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
    if new_body == selected.content:
        raise EditError("The proposed edit makes no change.")
    if any(c in SECTION_COMMANDS for c, *_ in _commands(_mask(new_body))):
        raise EditError("A section body cannot add or change section headings.")
    if _protected(selected.content) != _protected(new_body):
        raise EditError("A section edit cannot change template commands or file dependencies.")
    if _profile(selected.content) != _profile(new_body):
        raise EditError("The edit would break surrounding braces or environments.")
    if _mask(new_body.rsplit("\n", 1)[-1]) != new_body.rsplit("\n", 1)[-1]:
        raise EditError("A trailing LaTeX comment must end with a newline.")
    source = _decode(old_bytes)
    updated = (source[:selected.start] + new_body + source[selected.end:]).encode("utf-8")
    if old_bytes.startswith(b"\xef\xbb\xbf"):
        updated = b"\xef\xbb\xbf" + updated
    files = dict(project.files)
    files[selected.file] = updated
    return replace(project, files=files)
