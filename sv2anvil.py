#!/usr/bin/env python3
"""sv2anvil.py — Convert SystemVerilog to Anvil HDL.

Usage:
    python3 sv2anvil.py input.sv output.anvil

This is a regex-based best-effort converter.  It handles the most common SV
constructs and emits syntactically valid Anvil.  Unsupported constructs are
printed as warnings to stderr and inserted as comments in the output.
"""

import re
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def warn(msg: str) -> None:
    """Print a conversion warning to stderr."""
    print(f"WARNING: {msg}", file=sys.stderr)


def anvil_width_type(msb: str, lsb: str) -> str:
    """Convert [msb:lsb] to Anvil type.  Returns e.g. '(logic[8])'."""
    try:
        width = int(msb) - int(lsb) + 1
        if width == 1:
            return "logic"
        return f"(logic[{width}])"
    except ValueError:
        # Parametric width — keep as expression
        # e.g. CVA6Cfg.XLEN-1 : 0  =>  (logic[CVA6Cfg.XLEN])
        msb_s = msb.strip()
        lsb_s = lsb.strip()
        if lsb_s == "0":
            # Simplify: if msb is "X-1", width is just "X"
            m = re.match(r"^(.+?)\s*-\s*1$", msb_s)
            if m:
                return f"(logic[{m.group(1).strip()}])"
            return f"(logic[{msb_s} + 1])"
        return f"(logic[{msb_s} - {lsb_s} + 1])"


def convert_literal(lit: str) -> str:
    """Convert an SV numeric literal to Anvil format.

    SV:   32'd0, 8'hFF, 1'b1, 'b0, '0, '1
    Anvil: 32'd0, 8'hFF, 1'b1, 1'b0, 1'b0, 1'b1  (width-prefixed)
    """
    # Already width-prefixed: 8'hFF etc.
    m = re.match(r"(\d+)'([bdho])([0-9a-fA-F_xXzZ]+)", lit)
    if m:
        return lit  # pass through, Anvil uses same format

    # Unsized: 'b0, 'h1A
    m = re.match(r"'([bdho])([0-9a-fA-F_xXzZ]+)", lit)
    if m:
        base, digits = m.group(1), m.group(2)
        width = 1 if base == "b" else len(digits) * 4
        return f"{width}'{base}{digits}"

    # '0 and '1 shorthand
    if lit == "'0":
        return "1'b0"
    if lit == "'1":
        return "1'b1"

    return lit


_LITERAL_RE = re.compile(r"(\d+)'([bdho])([0-9a-fA-F_xXzZ]+)|'([bdho])([0-9a-fA-F_xXzZ]+)|'[01]")


def convert_literals_in_expr(expr: str) -> str:
    """Replace all SV literals inside an expression."""
    return _LITERAL_RE.sub(lambda m: convert_literal(m.group(0)), expr)


def find_balanced_parens(text: str, start: int = 0) -> Tuple[int, int]:
    """Find balanced parentheses starting from *start*.

    Returns (open_idx, close_idx) of the balanced pair, or (-1, -1) if not found.
    """
    idx = text.find("(", start)
    if idx == -1:
        return (-1, -1)
    depth = 0
    for i in range(idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return (idx, i)
    return (idx, -1)


def extract_if_condition(text: str, if_pos: int) -> Optional[Tuple[str, int]]:
    """Extract the full condition from an if statement using balanced parens.

    Returns (condition_string, end_pos_after_close_paren) or None.
    """
    rest = text[if_pos:]
    m = re.match(r"if\s*", rest)
    if not m:
        return None
    paren_start = if_pos + m.end()
    if paren_start >= len(text) or text[paren_start] != "(":
        return None
    open_idx, close_idx = find_balanced_parens(text, paren_start)
    if close_idx == -1:
        return None
    condition = text[open_idx + 1 : close_idx].strip()
    return (condition, close_idx + 1)


# ---------------------------------------------------------------------------
# Port / signal data
# ---------------------------------------------------------------------------

@dataclass
class Port:
    name: str
    direction: str  # input, output, inout
    width_type: str  # Anvil type string
    raw: str  # original declaration for reference


@dataclass
class Signal:
    name: str
    width_type: str
    raw: str


# ---------------------------------------------------------------------------
# Clock/reset detection
# ---------------------------------------------------------------------------

_CLK_NAMES = {"clk", "clk_i", "clk_o", "clock", "CLK"}
_RST_NAMES = {"rst", "rst_i", "rst_ni", "rst_n", "reset", "RST", "rst_o", "areset"}


def is_clk_or_rst(name: str) -> bool:
    return name in _CLK_NAMES or name in _RST_NAMES


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_PORT_RE = re.compile(
    r"(input|output|inout)\s+(\w+)?\s*"
    r"(?:\[([^\]]+):([^\]]+)\])?\s*"
    r"(\w+)",
)

_SIGNAL_RE = re.compile(
    r"^\s*(logic|wire|reg)\s*"
    r"(?:\[([^\]]+):([^\]]+)\])?\s*"
    r"(\w+(?:\s*,\s*\w+)*)\s*;",
    re.MULTILINE,
)

_ASSIGN_RE = re.compile(
    r"^\s*assign\s+(\w+(?:\[[^\]]*\])?)\s*=\s*(.+?)\s*;",
    re.MULTILINE,
)

_PARAM_RE = re.compile(
    r"parameter\s+.*?\b(\w+)\s*=\s*([^,\)]+)",
)


def parse_ports(port_block: str) -> List[Port]:
    """Extract ports from the module port list."""
    ports: List[Port] = []
    for m in _PORT_RE.finditer(port_block):
        direction = m.group(1)
        type_kw = m.group(2)  # logic, wire, reg, or custom type name
        msb, lsb = m.group(3), m.group(4)
        name = m.group(5)
        if msb and lsb:
            wtype = anvil_width_type(msb, lsb)
        elif type_kw and type_kw not in ("logic", "wire", "reg"):
            wtype = type_kw  # custom type — pass through
        else:
            wtype = "logic"
        ports.append(Port(name=name, direction=direction, width_type=wtype, raw=m.group(0)))
    return ports


def parse_signals(body: str) -> List[Signal]:
    """Extract signal declarations from the module body."""
    signals: List[Signal] = []
    for m in _SIGNAL_RE.finditer(body):
        msb, lsb = m.group(2), m.group(3)
        names_str = m.group(4)
        if msb and lsb:
            wtype = anvil_width_type(msb, lsb)
        else:
            wtype = "logic"
        for name in re.split(r"\s*,\s*", names_str):
            name = name.strip()
            if name:
                signals.append(Signal(name=name, width_type=wtype, raw=m.group(0)))
    return signals


# ---------------------------------------------------------------------------
# Block extraction
# ---------------------------------------------------------------------------

def find_balanced_braces(text: str, start: int) -> Tuple[int, int]:
    """Return (open, close) indices of balanced braces starting from *start*.

    *start* should point at or before the first '{'.
    """
    idx = text.find("{", start)
    if idx == -1:
        return (-1, -1)
    depth = 0
    for i in range(idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return (idx, i)
    return (idx, -1)


def find_begin_end(text: str, start: int) -> Tuple[int, int]:
    """Find balanced begin/end block starting from *start*.

    Returns (begin_pos, end_pos) where begin_pos is the index of 'begin'
    and end_pos is the index right after the matching 'end'.
    """
    # Find the first 'begin' keyword
    bm = re.search(r"\bbegin\b", text[start:])
    if not bm:
        return (-1, -1)
    begin_pos = start + bm.start()
    depth = 0
    # Tokenize begin/end keywords
    for km in re.finditer(r"\b(begin|end)\b", text[begin_pos:]):
        if km.group(1) == "begin":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return (begin_pos, begin_pos + km.end())
    return (begin_pos, -1)


def extract_always_blocks(body: str):
    """Yield (kind, label_or_empty, block_body) for each always block."""
    for m in re.finditer(r"always_(comb|ff)\b", body):
        kind = m.group(1)
        # Find the begin/end block
        begin_pos, end_pos = find_begin_end(body, m.end())
        if begin_pos == -1 or end_pos == -1:
            # Try brace-delimited as fallback
            open_idx, close_idx = find_balanced_braces(body, m.start())
            if open_idx == -1 or close_idx == -1:
                continue
            inner = body[open_idx + 1 : close_idx].strip()
        else:
            # Extract between begin and end
            # Skip past "begin" keyword and optional label
            after_begin = re.match(r"\s*begin\s*(?::\s*\w+)?\s*", body[begin_pos:])
            inner_start = begin_pos + after_begin.end() if after_begin else begin_pos + 5
            # end_pos points right after "end" — inner is up to the "end" keyword
            inner_end = end_pos - 3  # len("end") = 3
            inner = body[inner_start:inner_end].strip()
        # Check for a label in the "begin : label" part
        label_text = body[m.end():begin_pos + 30] if begin_pos != -1 else ""
        label_m = re.search(r"begin\s*:\s*(\w+)", label_text)
        label = label_m.group(1) if label_m else ""
        yield (kind, label, inner)


def extract_case_blocks(block: str):
    """Yield (selector_expr, [(pattern, body), ...]) for case/unique case."""
    for m in re.finditer(r"(?:unique\s+)?case\s*\(([^)]+)\)", block):
        selector = m.group(1).strip()
        # Find the matching endcase
        ec = block.find("endcase", m.end())
        if ec == -1:
            continue
        case_body = block[m.end() : ec]
        items: List[Tuple[str, str]] = []
        # Match case items: pattern at start of line followed by ':'
        # but NOT inside brackets like [31:0].
        # Pattern: line-start, optional whitespace, identifiers/commas, then ':'
        for cm in re.finditer(r"^[ \t]*((?:\w+(?:\s*,\s*\w+)*))\s*:", case_body, re.MULTILINE):
            pat = cm.group(1).strip()
            # Skip if this looks like a label inside a nested block
            if pat in ("begin", "end"):
                continue
            rest_start = cm.end()
            # Find next case item (line starting with identifier(s) followed by :)
            next_m = re.search(r"^[ \t]*(?:\w+(?:\s*,\s*\w+)*)\s*:", case_body[rest_start:], re.MULTILINE)
            if next_m:
                cbody = case_body[rest_start : rest_start + next_m.start()].strip().rstrip(";")
            else:
                cbody = case_body[rest_start:].strip().rstrip(";")
            items.append((pat, cbody))
        yield (selector, items)


# ---------------------------------------------------------------------------
# Expression converter
# ---------------------------------------------------------------------------

def _mask_brackets(text: str) -> str:
    """Replace content inside [...] with underscores to protect colons in bit slices."""
    result = list(text)
    depth = 0
    for i, ch in enumerate(text):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        elif depth > 0:
            result[i] = "_"
    return "".join(result)


def convert_expr(expr: str) -> str:
    """Best-effort conversion of an SV expression to Anvil."""
    e = expr.strip().rstrip(";")
    e = convert_literals_in_expr(e)
    # $signed(...) / $unsigned(...) — strip, just keep inner
    e = re.sub(r"\$(?:signed|unsigned)\s*\(", "(", e)
    # $clog2(...) — keep as-is (comment it)
    # Ternary: a ? b : c  →  if a { b } else { c }
    # Only convert simple one-level ternaries.
    # Bug fix: mask bracket content so ':' inside [5:0] is not matched as ternary.
    if "?" in e and e.count("?") == 1:
        # Mask [...] content with placeholders to protect bit-slice colons
        masked = _mask_brackets(e)
        tm = re.match(r"^(.+?)\s*\?\s*(.+?)\s*:\s*(.+)$", masked)
        if tm:
            # Use the same span positions on the original string
            cond = e[tm.start(1):tm.end(1)].strip()
            t_val = e[tm.start(2):tm.end(2)].strip()
            f_val = e[tm.start(3):tm.end(3)].strip()
            e = f"if {cond} {{ {t_val} }} else {{ {f_val} }}"
    # Concatenation: {a, b, c} → #{{ a, b, c }}
    e = re.sub(r"\{([^{}]+)\}", lambda m: f"#{{ {m.group(1)} }}", e)
    # Replication: N{expr} inside concat — leave as comment for now
    return e


def convert_case_to_match(selector: str, items, indent: str = "    ") -> str:
    """Convert a parsed case block to an Anvil match expression."""
    lines = [f"{indent}match {convert_expr(selector)} {{"]
    has_default = False
    for pat, body in items:
        body_stripped = body.strip().rstrip(';') if body else ''
        am = re.match(r'(\w+(?:\[[^\]]*\])?)\s*=\s*(.+)', body_stripped)
        if am:
            converted_body = f'let {am.group(1)} = {convert_expr(am.group(2))}'
        elif body:
            converted_body = convert_expr(body)
        else:
            converted_body = '()'
        if pat == "default":
            has_default = True
            lines.append(f"{indent}    _ => {converted_body},")
        else:
            lines.append(f"{indent}    {pat} => {converted_body},")
    if not has_default:
        lines.append(f"{indent}    _ => (),")
    lines.append(f"{indent}}}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Always-block converters
# ---------------------------------------------------------------------------

def _find_case_spans(inner: str) -> List[Tuple[int, int]]:
    """Find spans of case/unique case ... endcase blocks."""
    spans: List[Tuple[int, int]] = []
    for m in re.finditer(r"(?:unique\s+)?case\s*\(", inner):
        ec = inner.find("endcase", m.start())
        if ec != -1:
            spans.append((m.start(), ec + len("endcase")))
    return spans


def _find_if_spans(inner: str) -> List[Tuple[int, int]]:
    """Find spans of if (...) begin...end [else begin...end] blocks."""
    spans: List[Tuple[int, int]] = []
    for m in re.finditer(r"\bif\s*\(", inner):
        result = extract_if_condition(inner, m.start())
        if not result:
            continue
        _, after_cond = result
        rest = inner[after_cond:]
        bm = re.match(r"\s*begin\b", rest)
        if bm:
            bp, ep = find_begin_end(inner, after_cond)
            if bp != -1 and ep != -1:
                end = ep
                after_end = inner[ep:].lstrip()
                if after_end.startswith("else"):
                    else_start = ep + inner[ep:].index("else")
                    bp2, ep2 = find_begin_end(inner, else_start)
                    if bp2 != -1 and ep2 != -1:
                        end = ep2
                spans.append((m.start(), end))
        else:
            # Single-statement if: find the semicolon
            sc = inner.find(";", after_cond)
            if sc != -1:
                spans.append((m.start(), sc + 1))
    return spans


def _find_structured_spans(inner: str) -> List[Tuple[int, int]]:
    """Find all structured spans (case + if blocks)."""
    return _find_case_spans(inner) + _find_if_spans(inner)


def _pos_inside_spans(pos: int, spans: List[Tuple[int, int]]) -> bool:
    """Check if a position falls inside any structured span."""
    for start, end in spans:
        if start < pos < end:
            return True
    return False


def _convert_if_else_block(inner: str, if_pos: int, indent: str) -> Optional[str]:
    """Convert an if/else block structurally to Anvil."""
    result = extract_if_condition(inner, if_pos)
    if not result:
        return None
    cond_str, after_cond = result
    cond_anvil = convert_expr(cond_str)

    lines = [f"{indent}if {cond_anvil} {{"]

    # Find the then-body
    rest = inner[after_cond:]
    bm = re.match(r"\s*begin\b", rest)
    if bm:
        bp, ep = find_begin_end(inner, after_cond)
        if bp == -1 or ep == -1:
            return None
        after_begin = re.match(r"\s*begin\s*(?::\s*\w+)?\s*", inner[bp:])
        inner_start = bp + after_begin.end() if after_begin else bp + 5
        inner_end = ep - 3
        then_body = inner[inner_start:inner_end].strip()
        # Recursively convert the then-body
        lines.append(_convert_comb_body(then_body, indent + "    "))
        lines.append(f"{indent}}}")

        # Check for else
        after_end_str = inner[ep:].lstrip()
        if after_end_str.startswith("else"):
            else_start = ep + inner[ep:].index("else")
            after_else = inner[else_start + 4:].lstrip()
            if after_else.startswith("if"):
                # else if — recurse
                if_start = else_start + 4 + (len(inner[else_start + 4:]) - len(after_else))
                else_part = _convert_if_else_block(inner, if_start, indent)
                if else_part:
                    # Replace the leading indent + "if" with "else if"
                    lines[-1] = f"{indent}}} else {else_part.lstrip()}"
            elif after_else.startswith("begin"):
                bp2, ep2 = find_begin_end(inner, else_start + 4)
                if bp2 != -1 and ep2 != -1:
                    after_begin2 = re.match(r"\s*begin\s*(?::\s*\w+)?\s*", inner[bp2:])
                    inner_start2 = bp2 + after_begin2.end() if after_begin2 else bp2 + 5
                    inner_end2 = ep2 - 3
                    else_body = inner[inner_start2:inner_end2].strip()
                    lines[-1] = f"{indent}}} else {{"
                    lines.append(_convert_comb_body(else_body, indent + "    "))
                    lines.append(f"{indent}}}")
            else:
                # Single-statement else
                sc = inner.find(";", else_start + 4)
                if sc != -1:
                    else_stmt = inner[else_start + 4:sc].strip()
                    am = re.match(r"(\w+(?:\[[^\]]*\])?)\s*=\s*(.+)", else_stmt)
                    if am:
                        lines[-1] = f"{indent}}} else {{"
                        lines.append(f"{indent}    let {am.group(1)} = {convert_expr(am.group(2))};")
                        lines.append(f"{indent}}}")
    else:
        # Single-statement then
        sc = inner.find(";", after_cond)
        if sc != -1:
            then_stmt = inner[after_cond:sc].strip()
            am = re.match(r"(\w+(?:\[[^\]]*\])?)\s*=\s*(.+)", then_stmt)
            if am:
                lines.append(f"{indent}    let {am.group(1)} = {convert_expr(am.group(2))};")
            else:
                lines.append(f"{indent}    {convert_expr(then_stmt)};")
        lines.append(f"{indent}}}")

    return "\n".join(lines)


def _convert_comb_body(inner: str, indent: str) -> str:
    """Recursively convert an always_comb body, preserving structure."""
    top_level_assigns: List[str] = []
    case_lines: List[str] = []
    if_lines: List[str] = []
    case_spans = _find_case_spans(inner)
    if_spans = _find_if_spans(inner)
    all_spans = case_spans + if_spans

    # 1. Collect top-level assignments NOT inside any structured span
    #    (SV defaults — emitted first so they precede match/if blocks)
    for am in re.finditer(r"(\w+(?:\[[^\]]*\])?)\s*=\s*([^;]+);", inner):
        if not _pos_inside_spans(am.start(), all_spans):
            lhs = am.group(1)
            rhs = convert_expr(am.group(2))
            top_level_assigns.append(f"{indent}let {lhs} = {rhs};")

    # 2. Emit top-level case blocks (not inside any if-span)
    for m in re.finditer(r"(?:unique\s+)?case\s*\(", inner):
        if _pos_inside_spans(m.start(), if_spans):
            continue  # inside an if block — will be handled by recursive call
        # Also skip if inside another case block
        if _pos_inside_spans(m.start(), [(s, e) for s, e in case_spans if s != m.start()]):
            continue
        ec = inner.find("endcase", m.start())
        if ec == -1:
            continue
        selector_m = re.match(r"(?:unique\s+)?case\s*\(([^)]+)\)", inner[m.start():])
        if not selector_m:
            continue
        # Use extract_case_blocks on just this case block region
        case_region = inner[m.start():ec + len("endcase")]
        for selector, items in extract_case_blocks(case_region):
            case_lines.append(convert_case_to_match(selector, items, indent))

    # 3. Emit top-level if/else blocks (not inside any other span)
    for m in re.finditer(r"\bif\s*\(", inner):
        if _pos_inside_spans(m.start(), [(s, e) for s, e in all_spans if s != m.start()]):
            continue  # nested inside another structure
        converted = _convert_if_else_block(inner, m.start(), indent)
        if converted:
            if_lines.append(converted)

    lines = top_level_assigns + case_lines + if_lines

    if not lines:
        for l in inner.splitlines():
            stripped = l.strip()
            if stripped:
                lines.append(f"{indent}// [comb] {stripped}")
    return "\n".join(lines)


def convert_always_comb(inner: str, indent: str = "    ") -> str:
    """Convert an always_comb body to Anvil let-bindings and match exprs.

    Structure-aware: keeps assignments inside their case/if structures
    instead of flattening everything to top-level let bindings.
    """
    return _convert_comb_body(inner, indent)


def convert_always_ff(inner: str, indent: str = "    ") -> str:
    """Convert an always_ff body to Anvil reg + set statements."""
    lines: List[str] = []
    # Non-blocking assignments: lhs <= rhs;
    for m in re.finditer(r"(\w+(?:\[[^\]]*\])?)\s*<=\s*([^;]+);", inner):
        lhs = m.group(1)
        rhs = convert_expr(m.group(2))
        lines.append(f"{indent}set {lhs} := {rhs};")

    # case blocks inside always_ff
    for selector, items in extract_case_blocks(inner):
        ff_items = []
        for pat, body in items:
            # Convert <= to set :=
            body_c = re.sub(r"(\w+)\s*<=\s*([^;]+)", lambda m2: f"set {m2.group(1)} := {convert_expr(m2.group(2))}", body)
            ff_items.append((pat, body_c))
        lines.append(convert_case_to_match(selector, ff_items, indent))

    if not lines:
        for l in inner.splitlines():
            lines.append(f"{indent}// [ff] {l.strip()}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def strip_comments(sv: str) -> str:
    """Remove single-line and block comments from SV source."""
    # Remove block comments /* ... */
    sv = re.sub(r"/\*.*?\*/", "", sv, flags=re.DOTALL)
    # Remove single-line comments // ...
    sv = re.sub(r"//[^\n]*", "", sv)
    return sv


def convert_sv_to_anvil(sv_source: str) -> str:
    """Convert a SystemVerilog source string to Anvil HDL."""
    out: List[str] = []

    # Strip comments to avoid false matches (e.g., "module" in comments)
    sv_clean = strip_comments(sv_source)

    # --- Extract module name ------------------------------------------------
    mod_m = re.search(r"\bmodule\s+(\w+)", sv_clean)
    if not mod_m:
        warn("No module declaration found")
        return "// sv2anvil: no module found in input\n"
    module_name = mod_m.group(1)

    # --- Find module body boundaries ----------------------------------------
    # SV modules use ); ... endmodule (not brace-delimited)
    # Find the port-list closing ");".  We need the *last* ); before the
    # first signal/assign/always/generate statement to avoid matching ");'
    # inside expressions.  Strategy: find "); " that is followed by a newline
    # at the start of a line (the true port-list terminator).
    port_end = -1
    search_start = mod_m.end()
    while True:
        idx = sv_clean.find(");", search_start)
        if idx == -1:
            break
        # Check that this ); is at the end of a line (module port list)
        rest = sv_clean[idx + 2 : idx + 4]
        if rest.startswith("\n") or rest.startswith("\r") or idx + 2 >= len(sv_clean):
            port_end = idx
            break
        search_start = idx + 2

    if port_end == -1:
        warn("Cannot find module port list terminator );")
        return f"// sv2anvil: cannot parse module {module_name}\n"

    body_start = port_end + 2
    body_end_m = re.search(r"\bendmodule\b", sv_clean[body_start:])
    if body_end_m:
        body = sv_clean[body_start : body_start + body_end_m.start()]
    else:
        body = sv_clean[body_start:]
    # Port block is between module declaration and );
    port_block = sv_clean[mod_m.end() : port_end]

    # --- Parameters ---------------------------------------------------------
    params = _PARAM_RE.findall(sv_clean[mod_m.start() : mod_m.start() + len(port_block) + 200])
    if params:
        out.append(f"// Parameters (from SV — adapt manually):")
        for pname, pval in params:
            out.append(f"// param {pname} = {pval.strip()}")
        out.append("")

    # --- Imports / package references ---------------------------------------
    for im in re.finditer(r"import\s+([\w:*]+)\s*;", sv_clean):
        out.append(f"// import {im.group(1)} (SV package — adapt manually)")
    if re.search(r"import\s+", sv_clean):
        out.append("")

    # --- Parse ports --------------------------------------------------------
    ports = parse_ports(port_block)
    # Filter out clk/rst
    anvil_ports = [p for p in ports if not is_clk_or_rst(p.name)]
    clk_rst_ports = [p for p in ports if is_clk_or_rst(p.name)]
    if clk_rst_ports:
        out.append("// Clock/reset ports removed (implicit in Anvil):")
        for p in clk_rst_ports:
            out.append(f"//   {p.raw.strip()}")
        out.append("")

    # Build endpoint list
    endpoints: List[str] = []
    for p in anvil_ports:
        # input → right (data flows in), output → left (data flows out)
        if p.direction == "input":
            ep_dir = "right"
        elif p.direction == "output":
            ep_dir = "left"
        else:
            ep_dir = "left"  # inout → left with a warning
            warn(f"inout port '{p.name}' mapped to 'left' — review manually")
        # For a basic converter, we define a simple channel class per port
        endpoints.append(f"    {p.name} : {ep_dir} {p.width_type}")

    # --- Emit proc ----------------------------------------------------------
    ep_str = ",\n".join(endpoints)
    out.append(f"proc {module_name} (")
    out.append(ep_str)
    out.append(") {")

    # --- Parse and emit signals (let bindings) ------------------------------
    signals = parse_signals(body)
    if signals:
        out.append("    // Signal declarations")
        for sig in signals:
            out.append(f"    reg {sig.name} : {sig.width_type};")
        out.append("")

    # --- Assign statements → let bindings -----------------------------------
    assigns = _ASSIGN_RE.findall(body)
    if assigns:
        out.append("    // Combinational assignments")
        for lhs, rhs in assigns:
            out.append(f"    let {lhs} = {convert_expr(rhs)};")
        out.append("")

    # --- Generate blocks → comments + unrolled if simple --------------------
    for gm in re.finditer(r"\bgenerate\b", body):
        eg = body.find("endgenerate", gm.end())
        if eg == -1:
            continue
        gen_body = body[gm.end() : eg]
        out.append("    // [generate block — review and convert manually]")
        for line in gen_body.strip().splitlines():
            sl = line.strip()
            if sl:
                out.append(f"    // {sl}")
        out.append("")

    # --- Always blocks ------------------------------------------------------
    for kind, label, inner in extract_always_blocks(body):
        if label:
            out.append(f"    // always_{kind} : {label}")
        else:
            out.append(f"    // always_{kind}")
        if kind == "comb":
            out.append(convert_always_comb(inner, "    "))
        else:
            out.append("    loop {")
            out.append(convert_always_ff(inner, "        "))
            out.append("    }")
        out.append("")

    # --- Sub-module instantiations → spawn ----------------------------------
    # Pattern: module_name #(...) instance_name (...);
    inst_re = re.compile(r"(\w+)\s*#\s*\(([^)]*)\)\s*(\w+)\s*\(([^)]*)\)\s*;", re.DOTALL)
    for im in inst_re.finditer(body):
        mod = im.group(1)
        params_str = im.group(2).strip()
        inst = im.group(3)
        conn_str = im.group(4).strip()
        out.append(f"    // Instantiation: {mod} {inst}")
        out.append(f"    spawn {mod} /* {params_str} */ (")
        # Convert .port(signal) connections
        for cm in re.finditer(r"\.(\w+)\s*\(([^)]*)\)", conn_str):
            pname, sig = cm.group(1), cm.group(2).strip()
            out.append(f"        {pname} = {sig},")
        out.append(f"    );  // {inst}")
        out.append("")

    # --- Conditional generate (if blocks at module level) -------------------
    # e.g., if (CVA6Cfg.RVB) begin : gen_bitmanip ... end
    for cg in re.finditer(r"\bif\s*\(", body):
        result = extract_if_condition(body, cg.start())
        if not result:
            continue
        cond, after_cond = result
        # Check for begin with optional label after the condition
        rest_after = body[after_cond:]
        lm = re.match(r"\s*begin\s*(?::\s*(\w+))?\s*\n", rest_after)
        if not lm:
            continue
        label = lm.group(1) or ""
        out.append(f"    // Conditional block: if ({cond}) {label}")
        # Find matching end
        cg_open, cg_close = find_balanced_braces(body, cg.start())
        if cg_open != -1 and cg_close != -1:
            inner_cg = body[cg_open + 1 : cg_close]
            # Check for sub-module instantiations inside
            for im in inst_re.finditer(inner_cg):
                mod = im.group(1)
                inst = im.group(3)
                out.append(f"    // spawn {mod} ({inst}) — inside conditional, review manually")
        out.append("")

    out.append("}")
    out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 sv2anvil.py <input.sv> [output.anvil]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    with open(input_path, "r") as f:
        sv_source = f.read()

    anvil_output = convert_sv_to_anvil(sv_source)

    if output_path:
        with open(output_path, "w") as f:
            f.write(anvil_output)
        print(f"Converted {input_path} → {output_path}", file=sys.stderr)
    else:
        print(anvil_output)


if __name__ == "__main__":
    main()
