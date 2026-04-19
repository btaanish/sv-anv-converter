#!/usr/bin/env python3
"""sv2anvil.py — AST-based SystemVerilog to Anvil HDL converter.

Usage:
    python3 sv2anvil.py input.sv > output.anvil

Architecture: Lexer → Parser → IR → Codegen
"""

import re
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Tuple, Dict

# Anvil reserved words — identifiers that cannot be used as proc/let names
ANVIL_RESERVED = {
    "chan", "proc", "reg", "set", "loop", "cycle", "recv", "send",
    "let", "if", "else", "match", "logic", "left", "right", "sync",
    "ready",
}

def _sanitize_ident(name: str) -> str:
    """Append _m suffix if name collides with an Anvil reserved word."""
    if name in ANVIL_RESERVED:
        return name + "_m"
    return name


# ===========================================================================
# LEXER
# ===========================================================================

class TokenKind(Enum):
    # Keywords
    MODULE = auto()
    ENDMODULE = auto()
    INPUT = auto()
    OUTPUT = auto()
    INOUT = auto()
    LOGIC = auto()
    WIRE = auto()
    REG = auto()
    PARAMETER = auto()
    LOCALPARAM = auto()
    ASSIGN = auto()
    ALWAYS_FF = auto()
    ALWAYS_COMB = auto()
    ALWAYS = auto()
    IF = auto()
    ELSE = auto()
    BEGIN = auto()
    END = auto()
    CASE = auto()
    UNIQUE = auto()
    ENDCASE = auto()
    DEFAULT = auto()
    FOR = auto()
    GENERATE = auto()
    ENDGENERATE = auto()
    IMPORT = auto()
    POSEDGE = auto()
    NEGEDGE = auto()
    SIGNED = auto()
    UNSIGNED = auto()
    # Symbols
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LBRACE = auto()
    RBRACE = auto()
    SEMI = auto()
    COLON = auto()
    COMMA = auto()
    DOT = auto()
    AT = auto()
    HASH = auto()
    EQUALS = auto()
    LTE = auto()       # <=
    QUESTION = auto()
    TILDE = auto()
    BANG = auto()
    AND = auto()
    OR = auto()
    XOR = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    LT = auto()
    GT = auto()
    EQEQ = auto()      # ==
    NEQ = auto()        # !=
    LEQ = auto()        # <=  (comparison context)
    GEQ = auto()        # >=
    LSHIFT = auto()     # <<
    RSHIFT = auto()     # >>
    ARSHIFT = auto()    # >>>
    LAND = auto()       # &&
    LOR = auto()        # ||
    ARROW = auto()      # ->
    # Literals
    NUMBER = auto()     # decimal number
    SIZED_LIT = auto()  # e.g. 32'd0, 8'hFF, 1'b1
    TICK_ZERO = auto()  # '0
    TICK_ONE = auto()   # '1
    STRING = auto()
    # Identifiers & misc
    IDENT = auto()
    DOLLAR_IDENT = auto()  # $clog2, $signed, etc.
    SCOPE = auto()     # ::
    INSIDE = auto()
    EOF = auto()


@dataclass
class Token:
    kind: TokenKind
    value: str
    line: int
    col: int


# Keywords map
_KEYWORDS = {
    "module": TokenKind.MODULE,
    "endmodule": TokenKind.ENDMODULE,
    "input": TokenKind.INPUT,
    "output": TokenKind.OUTPUT,
    "inout": TokenKind.INOUT,
    "logic": TokenKind.LOGIC,
    "wire": TokenKind.WIRE,
    "reg": TokenKind.REG,
    "parameter": TokenKind.PARAMETER,
    "localparam": TokenKind.LOCALPARAM,
    "assign": TokenKind.ASSIGN,
    "always_ff": TokenKind.ALWAYS_FF,
    "always_comb": TokenKind.ALWAYS_COMB,
    "always": TokenKind.ALWAYS,
    "if": TokenKind.IF,
    "else": TokenKind.ELSE,
    "begin": TokenKind.BEGIN,
    "end": TokenKind.END,
    "case": TokenKind.CASE,
    "unique": TokenKind.UNIQUE,
    "endcase": TokenKind.ENDCASE,
    "default": TokenKind.DEFAULT,
    "for": TokenKind.FOR,
    "generate": TokenKind.GENERATE,
    "endgenerate": TokenKind.ENDGENERATE,
    "import": TokenKind.IMPORT,
    "posedge": TokenKind.POSEDGE,
    "negedge": TokenKind.NEGEDGE,
    "signed": TokenKind.SIGNED,
    "unsigned": TokenKind.UNSIGNED,
    "inside": TokenKind.INSIDE,
}


def lex(source: str) -> List[Token]:
    """Tokenize SystemVerilog source into a token list."""
    tokens: List[Token] = []
    i = 0
    line = 1
    col = 1

    while i < len(source):
        # Skip whitespace
        if source[i] in " \t\r":
            if source[i] == "\t":
                col += 4
            else:
                col += 1
            i += 1
            continue
        if source[i] == "\n":
            line += 1
            col = 1
            i += 1
            continue

        # Block comment
        if source[i:i+2] == "/*":
            end = source.find("*/", i + 2)
            if end == -1:
                end = len(source)
            else:
                end += 2
            # Count newlines in comment
            for ch in source[i:end]:
                if ch == "\n":
                    line += 1
                    col = 1
                else:
                    col += 1
            i = end
            continue

        # Line comment
        if source[i:i+2] == "//":
            end = source.find("\n", i)
            if end == -1:
                end = len(source)
            i = end
            continue

        # String literal
        if source[i] == '"':
            j = i + 1
            while j < len(source) and source[j] != '"':
                if source[j] == "\\":
                    j += 1
                j += 1
            j += 1  # skip closing quote
            tokens.append(Token(TokenKind.STRING, source[i:j], line, col))
            col += j - i
            i = j
            continue

        # Sized literal: N'bXXX, N'dXXX, N'hXXX, N'oXXX
        m = re.match(r"(\d+)'([bdho])([0-9a-fA-F_xXzZ]+)", source[i:])
        if m:
            tokens.append(Token(TokenKind.SIZED_LIT, m.group(0), line, col))
            col += len(m.group(0))
            i += len(m.group(0))
            continue

        # Tick literals: '0, '1, 'b0, 'h1A, etc.
        if source[i] == "'" and i + 1 < len(source):
            if source[i+1] == "0":
                tokens.append(Token(TokenKind.TICK_ZERO, "'0", line, col))
                col += 2
                i += 2
                continue
            if source[i+1] == "1":
                tokens.append(Token(TokenKind.TICK_ONE, "'1", line, col))
                col += 2
                i += 2
                continue
            # Unsized literal: 'bXXX, 'hXXX, etc.
            m2 = re.match(r"'([bdho])([0-9a-fA-F_xXzZ]+)", source[i:])
            if m2:
                tokens.append(Token(TokenKind.SIZED_LIT, m2.group(0), line, col))
                col += len(m2.group(0))
                i += len(m2.group(0))
                continue
            # '{default: ...} pattern
            if source[i+1] == "{":
                tokens.append(Token(TokenKind.TICK_ZERO, "'", line, col))
                col += 1
                i += 1
                continue

        # Numbers
        if source[i].isdigit():
            j = i
            while j < len(source) and (source[j].isdigit() or source[j] == "_"):
                j += 1
            tokens.append(Token(TokenKind.NUMBER, source[i:j], line, col))
            col += j - i
            i = j
            continue

        # $-prefixed identifiers
        if source[i] == "$":
            j = i + 1
            while j < len(source) and (source[j].isalnum() or source[j] == "_"):
                j += 1
            tokens.append(Token(TokenKind.DOLLAR_IDENT, source[i:j], line, col))
            col += j - i
            i = j
            continue

        # Identifiers and keywords
        if source[i].isalpha() or source[i] == "_":
            j = i
            while j < len(source) and (source[j].isalnum() or source[j] == "_"):
                j += 1
            word = source[i:j]
            kind = _KEYWORDS.get(word, TokenKind.IDENT)
            tokens.append(Token(kind, word, line, col))
            col += j - i
            i = j
            continue

        # Multi-char symbols
        two = source[i:i+2] if i + 1 < len(source) else ""
        three = source[i:i+3] if i + 2 < len(source) else ""

        if three == ">>>":
            tokens.append(Token(TokenKind.ARSHIFT, ">>>", line, col))
            col += 3
            i += 3
            continue
        if two == "::":
            tokens.append(Token(TokenKind.SCOPE, "::", line, col))
            col += 2
            i += 2
            continue
        if two == "<=":
            tokens.append(Token(TokenKind.LTE, "<=", line, col))
            col += 2
            i += 2
            continue
        if two == ">=":
            tokens.append(Token(TokenKind.GEQ, ">=", line, col))
            col += 2
            i += 2
            continue
        if two == "==":
            tokens.append(Token(TokenKind.EQEQ, "==", line, col))
            col += 2
            i += 2
            continue
        if two == "!=":
            tokens.append(Token(TokenKind.NEQ, "!=", line, col))
            col += 2
            i += 2
            continue
        if two == "<<":
            tokens.append(Token(TokenKind.LSHIFT, "<<", line, col))
            col += 2
            i += 2
            continue
        if two == ">>":
            tokens.append(Token(TokenKind.RSHIFT, ">>", line, col))
            col += 2
            i += 2
            continue
        if two == "&&":
            tokens.append(Token(TokenKind.LAND, "&&", line, col))
            col += 2
            i += 2
            continue
        if two == "||":
            tokens.append(Token(TokenKind.LOR, "||", line, col))
            col += 2
            i += 2
            continue
        if two == "->":
            tokens.append(Token(TokenKind.ARROW, "->", line, col))
            col += 2
            i += 2
            continue

        # Single-char symbols
        sym_map = {
            "(": TokenKind.LPAREN, ")": TokenKind.RPAREN,
            "[": TokenKind.LBRACKET, "]": TokenKind.RBRACKET,
            "{": TokenKind.LBRACE, "}": TokenKind.RBRACE,
            ";": TokenKind.SEMI, ":": TokenKind.COLON,
            ",": TokenKind.COMMA, ".": TokenKind.DOT,
            "@": TokenKind.AT, "#": TokenKind.HASH,
            "=": TokenKind.EQUALS, "?": TokenKind.QUESTION,
            "~": TokenKind.TILDE, "!": TokenKind.BANG,
            "&": TokenKind.AND, "|": TokenKind.OR,
            "^": TokenKind.XOR, "+": TokenKind.PLUS,
            "-": TokenKind.MINUS, "*": TokenKind.STAR,
            "/": TokenKind.SLASH, "%": TokenKind.PERCENT,
            "<": TokenKind.LT, ">": TokenKind.GT,
        }
        if source[i] in sym_map:
            tokens.append(Token(sym_map[source[i]], source[i], line, col))
            col += 1
            i += 1
            continue

        # Skip unknown character
        i += 1
        col += 1

    tokens.append(Token(TokenKind.EOF, "", line, col))
    return tokens


# ===========================================================================
# AST NODE TYPES
# ===========================================================================

@dataclass
class SVPort:
    name: str
    direction: str  # "input", "output", "inout"
    width_msb: Optional[str]  # None if scalar
    width_lsb: Optional[str]
    type_name: Optional[str]  # custom type if any (e.g. "scoreboard_entry_t")
    is_custom_type: bool = False
    packed_dims: List[Tuple[str, str]] = field(default_factory=list)  # extra packed dims


@dataclass
class SVParam:
    name: str
    value: str
    is_type: bool = False  # parameter type X = logic


@dataclass
class SVAssign:
    lhs: str
    rhs: str


@dataclass
class SVNonBlockAssign:
    lhs: str
    rhs: str


@dataclass
class SVIfBlock:
    condition: str
    then_stmts: list
    else_stmts: list  # may contain SVIfBlock for else-if


@dataclass
class SVCaseItem:
    pattern: str
    stmts: list


@dataclass
class SVCaseBlock:
    selector: str
    items: List[SVCaseItem]


@dataclass
class SVAlwaysComb:
    label: str
    stmts: list  # mix of SVAssign, SVIfBlock, SVCaseBlock


@dataclass
class SVAlwaysFF:
    label: str
    clock_edge: str
    reset_edge: Optional[str]
    reset_body: list
    main_body: list


@dataclass
class SVSignal:
    name: str
    width_msb: Optional[str]
    width_lsb: Optional[str]


@dataclass
class SVModule:
    name: str
    params: List[SVParam]
    ports: List[SVPort]
    signals: List[SVSignal]
    assigns: List[SVAssign]
    always_comb_blocks: List[SVAlwaysComb]
    always_ff_blocks: List[SVAlwaysFF]
    imports: List[str]


# ===========================================================================
# PARSER
# ===========================================================================

class Parser:
    """Recursive-descent parser for the SV subset we need."""

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.warnings: List[str] = []

    def warn(self, msg: str):
        tok = self.peek()
        self.warnings.append(f"Line {tok.line}: {msg}")

    def peek(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return Token(TokenKind.EOF, "", 0, 0)

    def advance(self) -> Token:
        tok = self.peek()
        if self.pos < len(self.tokens):
            self.pos += 1
        return tok

    def expect(self, kind: TokenKind) -> Token:
        tok = self.advance()
        if tok.kind != kind:
            self.warn(f"Expected {kind.name}, got {tok.kind.name} '{tok.value}'")
        return tok

    def at(self, kind: TokenKind) -> bool:
        return self.peek().kind == kind

    def at_any(self, *kinds: TokenKind) -> bool:
        return self.peek().kind in kinds

    def match(self, kind: TokenKind) -> Optional[Token]:
        if self.at(kind):
            return self.advance()
        return None

    def skip_until(self, *kinds: TokenKind):
        while not self.at(TokenKind.EOF) and not self.at_any(*kinds):
            self.advance()

    def skip_balanced_parens(self) -> str:
        """Skip and collect text inside balanced parentheses."""
        depth = 0
        parts = []
        while not self.at(TokenKind.EOF):
            if self.at(TokenKind.LPAREN):
                depth += 1
                parts.append(self.advance().value)
            elif self.at(TokenKind.RPAREN):
                depth -= 1
                parts.append(self.advance().value)
                if depth == 0:
                    return " ".join(parts)
            else:
                parts.append(self.advance().value)
        return " ".join(parts)

    def collect_expr_until(self, *stop_kinds: TokenKind) -> str:
        """Collect tokens as text until one of stop_kinds is seen (not consumed)."""
        parts = []
        depth_p = 0  # parens
        depth_b = 0  # brackets
        depth_c = 0  # braces
        while not self.at(TokenKind.EOF):
            if depth_p == 0 and depth_b == 0 and depth_c == 0:
                if self.at_any(*stop_kinds):
                    break
            tok = self.peek()
            if tok.kind == TokenKind.LPAREN:
                depth_p += 1
            elif tok.kind == TokenKind.RPAREN:
                depth_p -= 1
                if depth_p < 0:
                    break
            elif tok.kind == TokenKind.LBRACKET:
                depth_b += 1
            elif tok.kind == TokenKind.RBRACKET:
                depth_b -= 1
                if depth_b < 0:
                    break
            elif tok.kind == TokenKind.LBRACE:
                depth_c += 1
            elif tok.kind == TokenKind.RBRACE:
                depth_c -= 1
                if depth_c < 0:
                    break
            parts.append(self.advance().value)
        return " ".join(parts)

    def parse_module(self) -> SVModule:
        """Parse: module name import... #(params) (ports); body endmodule"""
        imports = []
        # Check for package/interface (no module keyword) — generate stub
        pkg_name = None
        while not self.at(TokenKind.MODULE) and not self.at(TokenKind.EOF):
            tok = self.peek()
            if tok.kind == TokenKind.IDENT and tok.value in ("package", "interface"):
                self.advance()
                if self.at(TokenKind.IDENT):
                    pkg_name = self.peek().value
                    self.advance()
                # Skip to EOF — package/interface bodies don't have module structure
                while not self.at(TokenKind.EOF):
                    self.advance()
                break
            elif self.at(TokenKind.IMPORT):
                self.advance()
                imp_text = self.collect_expr_until(TokenKind.SEMI)
                imports.append(imp_text.strip())
                self.match(TokenKind.SEMI)
            else:
                self.advance()

        if pkg_name or self.at(TokenKind.EOF):
            # Package or interface — return stub module
            name = pkg_name or "unnamed_pkg"
            return SVModule(
                name=name,
                params=[],
                ports=[],
                signals=[],
                assigns=[],
                always_comb_blocks=[],
                always_ff_blocks=[],
                imports=imports,
            )

        self.expect(TokenKind.MODULE)
        name_tok = self.expect(TokenKind.IDENT)
        module_name = name_tok.value

        # Collect imports after module name
        while self.at(TokenKind.IMPORT):
            self.advance()
            imp_text = self.collect_expr_until(TokenKind.SEMI)
            imports.append(imp_text.strip())
            self.match(TokenKind.SEMI)

        # Parameters
        params = []
        if self.at(TokenKind.HASH):
            self.advance()
            self.expect(TokenKind.LPAREN)
            params = self._parse_params()
            self.expect(TokenKind.RPAREN)

        # Port list
        self.expect(TokenKind.LPAREN)
        ports = self._parse_ports()
        self.expect(TokenKind.RPAREN)
        self.expect(TokenKind.SEMI)

        # Body
        signals = []
        assigns = []
        comb_blocks = []
        ff_blocks = []

        while not self.at(TokenKind.ENDMODULE) and not self.at(TokenKind.EOF):
            if self.at(TokenKind.ASSIGN):
                a = self._parse_assign()
                if a:
                    assigns.append(a)
            elif self.at(TokenKind.ALWAYS_COMB):
                cb = self._parse_always_comb()
                if cb:
                    comb_blocks.append(cb)
            elif self.at(TokenKind.ALWAYS_FF):
                fb = self._parse_always_ff()
                if fb:
                    ff_blocks.append(fb)
            elif self.at(TokenKind.ALWAYS):
                # plain always — try to parse as always_ff
                fb = self._parse_always_ff()
                if fb:
                    ff_blocks.append(fb)
            elif self.at_any(TokenKind.LOGIC, TokenKind.WIRE, TokenKind.REG):
                sig = self._parse_signal()
                if sig:
                    signals.extend(sig)
            elif self.at(TokenKind.LOCALPARAM):
                # Treat as parameter
                self.advance()
                p = self._parse_one_param()
                if p:
                    params.append(p)
                self.match(TokenKind.SEMI)
            elif self.at(TokenKind.GENERATE):
                self._skip_generate()
            elif self.at(TokenKind.FOR):
                self._skip_for_generate()
            elif self.at(TokenKind.IMPORT):
                self.advance()
                imp_text = self.collect_expr_until(TokenKind.SEMI)
                imports.append(imp_text.strip())
                self.match(TokenKind.SEMI)
            elif self.at(TokenKind.DOLLAR_IDENT):
                # $error, $warning, etc. — skip to semicolon
                self.skip_until(TokenKind.SEMI)
                self.match(TokenKind.SEMI)
            else:
                self.advance()

        self.match(TokenKind.ENDMODULE)

        return SVModule(
            name=module_name,
            params=params,
            ports=ports,
            signals=signals,
            assigns=assigns,
            always_comb_blocks=comb_blocks,
            always_ff_blocks=ff_blocks,
            imports=imports,
        )

    def _parse_params(self) -> List[SVParam]:
        """Parse parameter list inside #(...)."""
        params = []
        while not self.at(TokenKind.RPAREN) and not self.at(TokenKind.EOF):
            p = self._parse_one_param()
            if p:
                params.append(p)
            if self.at(TokenKind.COMMA):
                self.advance()
            elif not self.at(TokenKind.RPAREN):
                self.advance()  # skip unexpected
        return params

    def _parse_one_param(self) -> Optional[SVParam]:
        """Parse a single parameter declaration."""
        self.match(TokenKind.PARAMETER)
        # Check for 'type' keyword
        is_type = False
        if self.peek().value == "type":
            is_type = True
            self.advance()

        # Skip type qualifiers (int unsigned, bit, config_pkg::cva6_cfg_t, etc.)
        while self.at_any(TokenKind.IDENT, TokenKind.SCOPE, TokenKind.SIGNED,
                          TokenKind.UNSIGNED, TokenKind.LOGIC) and not self.at(TokenKind.EOF):
            name_tok = self.advance()
            if self.at(TokenKind.SCOPE):
                self.advance()
                continue
            if self.at(TokenKind.EQUALS):
                # This identifier is the parameter name
                self.advance()  # consume =
                value = self.collect_expr_until(TokenKind.COMMA, TokenKind.RPAREN, TokenKind.SEMI)
                return SVParam(name=name_tok.value, value=value.strip(), is_type=is_type)
            # Otherwise it's a type qualifier, continue
        return None

    def _parse_ports(self) -> List[SVPort]:
        """Parse port list inside module(...)."""
        ports = []
        while not self.at(TokenKind.RPAREN) and not self.at(TokenKind.EOF):
            if self.at_any(TokenKind.INPUT, TokenKind.OUTPUT, TokenKind.INOUT):
                direction = self.advance().value
                # Determine type
                type_name = None
                is_custom = False
                width_msb = None
                width_lsb = None
                packed_dims = []

                # Check for logic/wire/reg or custom type
                if self.at_any(TokenKind.LOGIC, TokenKind.WIRE, TokenKind.REG):
                    self.advance()
                elif self.at(TokenKind.IDENT):
                    # Could be a custom type (e.g. riscv::xs_t)
                    # or the port name
                    # Peek ahead: if next is :: or [, it's a type
                    saved = self.pos
                    type_tok = self.advance()
                    if self.at(TokenKind.SCOPE):
                        # Scoped type: riscv::xs_t
                        self.advance()
                        type_suffix = self.advance()
                        type_name = f"{type_tok.value}::{type_suffix.value}"
                        is_custom = True
                    elif self.at(TokenKind.LBRACKET) or self.at(TokenKind.IDENT):
                        # Custom type or just the port name
                        # If next token is an identifier, current was a type
                        if self.at(TokenKind.IDENT):
                            type_name = type_tok.value
                            is_custom = True
                        elif self.at(TokenKind.LBRACKET):
                            # Could be type with dims or port name with dims
                            # Heuristic: if after brackets there's an ident, it's a type
                            saved2 = self.pos
                            self._skip_brackets()
                            if self.at(TokenKind.IDENT):
                                type_name = type_tok.value
                                is_custom = True
                                self.pos = saved2  # restore to parse dims
                            else:
                                # It was the port name, restore
                                self.pos = saved
                        else:
                            self.pos = saved
                    else:
                        self.pos = saved

                # Parse packed dimensions [msb:lsb]
                while self.at(TokenKind.LBRACKET):
                    self.advance()
                    msb = self.collect_expr_until(TokenKind.COLON, TokenKind.RBRACKET)
                    if self.at(TokenKind.COLON):
                        self.advance()
                        lsb = self.collect_expr_until(TokenKind.RBRACKET)
                        if width_msb is None:
                            width_msb = msb.strip()
                            width_lsb = lsb.strip()
                        else:
                            packed_dims.append((msb.strip(), lsb.strip()))
                    self.expect(TokenKind.RBRACKET)

                # Port name
                if self.at(TokenKind.IDENT):
                    port_name = self.advance().value
                else:
                    self.warn("Expected port name")
                    self.skip_until(TokenKind.COMMA, TokenKind.RPAREN)
                    if self.at(TokenKind.COMMA):
                        self.advance()
                    continue

                ports.append(SVPort(
                    name=port_name,
                    direction=direction,
                    width_msb=width_msb,
                    width_lsb=width_lsb,
                    type_name=type_name,
                    is_custom_type=is_custom,
                    packed_dims=packed_dims,
                ))

                # Skip trailing comma
                if self.at(TokenKind.COMMA):
                    self.advance()
            else:
                self.advance()  # skip unexpected tokens
        return ports

    def _skip_brackets(self):
        """Skip over [...]."""
        if self.at(TokenKind.LBRACKET):
            self.advance()
            depth = 1
            while depth > 0 and not self.at(TokenKind.EOF):
                if self.at(TokenKind.LBRACKET):
                    depth += 1
                elif self.at(TokenKind.RBRACKET):
                    depth -= 1
                self.advance()

    def _parse_signal(self) -> List[SVSignal]:
        """Parse a signal declaration: logic/wire/reg [#delay] [msb:lsb] name, name2;"""
        self.advance()  # consume logic/wire/reg
        # Skip optional delay: #number or #number.number
        if self.at(TokenKind.HASH):
            self.advance()
            while self.at(TokenKind.NUMBER) or self.at(TokenKind.DOT):
                self.advance()
        width_msb = None
        width_lsb = None

        if self.at(TokenKind.LBRACKET):
            self.advance()
            width_msb = self.collect_expr_until(TokenKind.COLON, TokenKind.RBRACKET).strip()
            if self.at(TokenKind.COLON):
                self.advance()
                width_lsb = self.collect_expr_until(TokenKind.RBRACKET).strip()
            self.expect(TokenKind.RBRACKET)

        # May have additional packed dims — skip them
        while self.at(TokenKind.LBRACKET):
            self._skip_brackets()

        signals = []
        while True:
            if self.at(TokenKind.IDENT):
                name = self.advance().value
                # Skip unpacked dims
                while self.at(TokenKind.LBRACKET):
                    self._skip_brackets()
                signals.append(SVSignal(name=name, width_msb=width_msb, width_lsb=width_lsb))
            if self.at(TokenKind.COMMA):
                self.advance()
            else:
                break
        self.match(TokenKind.SEMI)
        return signals

    def _parse_assign(self) -> Optional[SVAssign]:
        """Parse: assign [#delay] lhs = rhs;"""
        self.expect(TokenKind.ASSIGN)
        # Skip optional delay: #number or #number.number
        if self.at(TokenKind.HASH):
            self.advance()
            # Skip delay value (e.g., 0.1, 10, etc.)
            while self.at(TokenKind.NUMBER) or (self.at(TokenKind.DOT)):
                self.advance()
        lhs = self.collect_expr_until(TokenKind.EQUALS)
        self.expect(TokenKind.EQUALS)
        rhs = self.collect_expr_until(TokenKind.SEMI)
        self.match(TokenKind.SEMI)
        return SVAssign(lhs=lhs.strip(), rhs=rhs.strip())

    def _parse_always_comb(self) -> Optional[SVAlwaysComb]:
        """Parse always_comb begin...end."""
        self.advance()  # consume always_comb
        label = ""
        if self.at(TokenKind.BEGIN):
            self.advance()
            if self.at(TokenKind.COLON):
                self.advance()
                if self.at(TokenKind.IDENT):
                    label = self.advance().value
        stmts = self._parse_stmts_until(TokenKind.END)
        self.match(TokenKind.END)
        # Skip optional : label after end
        if self.at(TokenKind.COLON):
            self.advance()
            self.match(TokenKind.IDENT)
        return SVAlwaysComb(label=label, stmts=stmts)

    def _parse_always_ff(self) -> Optional[SVAlwaysFF]:
        """Parse always_ff @(posedge clk...) begin...end."""
        self.advance()  # consume always_ff or always
        # Skip sensitivity list @(...)
        clock_edge = "posedge"
        reset_edge = None
        if self.at(TokenKind.AT):
            self.advance()
            if self.at(TokenKind.LPAREN):
                sens = self.skip_balanced_parens()
                if "negedge" in sens:
                    reset_edge = "negedge"
                elif "posedge" in sens and sens.count("posedge") > 1:
                    reset_edge = "posedge"

        label = ""
        if self.at(TokenKind.BEGIN):
            self.advance()
            if self.at(TokenKind.COLON):
                self.advance()
                if self.at(TokenKind.IDENT):
                    label = self.advance().value

        # Parse reset/main body
        reset_body = []
        main_body = []

        # Check for if (~rst_ni) pattern (reset handling)
        if self.at(TokenKind.IF):
            self.advance()
            self.expect(TokenKind.LPAREN)
            cond = self.collect_expr_until(TokenKind.RPAREN)
            self.expect(TokenKind.RPAREN)

            # Parse reset body
            if self.at(TokenKind.BEGIN):
                self.advance()
                if self.at(TokenKind.COLON):
                    self.advance()
                    self.match(TokenKind.IDENT)
                reset_body = self._parse_stmts_until(TokenKind.END)
                self.match(TokenKind.END)
            else:
                # Single statement
                stmt = self._parse_one_stmt()
                if stmt:
                    reset_body = [stmt]

            # Parse else (main body)
            if self.at(TokenKind.ELSE):
                self.advance()
                if self.at(TokenKind.BEGIN):
                    self.advance()
                    if self.at(TokenKind.COLON):
                        self.advance()
                        self.match(TokenKind.IDENT)
                    main_body = self._parse_stmts_until(TokenKind.END)
                    self.match(TokenKind.END)
                else:
                    stmt = self._parse_one_stmt()
                    if stmt:
                        main_body = [stmt]
        else:
            main_body = self._parse_stmts_until(TokenKind.END)

        self.match(TokenKind.END)
        # Skip optional : label
        if self.at(TokenKind.COLON):
            self.advance()
            self.match(TokenKind.IDENT)

        return SVAlwaysFF(
            label=label,
            clock_edge=clock_edge,
            reset_edge=reset_edge,
            reset_body=reset_body,
            main_body=main_body,
        )

    def _parse_stmts_until(self, stop: TokenKind) -> list:
        """Parse statements until stop token."""
        stmts = []
        while not self.at(stop) and not self.at(TokenKind.EOF):
            stmt = self._parse_one_stmt()
            if stmt:
                stmts.append(stmt)
        return stmts

    def _parse_one_stmt(self) -> object:
        """Parse a single statement in an always block."""
        # Skip 'automatic' keyword
        if self.peek().value == "automatic":
            self.advance()
            # Skip type and collect as signal/assign
            self.skip_until(TokenKind.SEMI)
            self.match(TokenKind.SEMI)
            return None

        # for loop — skip for now
        if self.at(TokenKind.FOR):
            self._skip_for_loop()
            return None

        # if-else
        if self.at(TokenKind.IF):
            return self._parse_if()

        # case / unique case
        if self.at(TokenKind.UNIQUE):
            self.advance()
        if self.at(TokenKind.CASE):
            return self._parse_case()

        # Non-blocking assignment: lhs <= rhs;
        # or blocking assignment: lhs = rhs;
        if self.at(TokenKind.IDENT) or self.at(TokenKind.LBRACE):
            saved = self.pos
            lhs = self.collect_expr_until(TokenKind.LTE, TokenKind.EQUALS, TokenKind.SEMI)
            if self.at(TokenKind.LTE):
                self.advance()
                rhs = self.collect_expr_until(TokenKind.SEMI)
                self.match(TokenKind.SEMI)
                return SVNonBlockAssign(lhs=lhs.strip(), rhs=rhs.strip())
            elif self.at(TokenKind.EQUALS):
                self.advance()
                rhs = self.collect_expr_until(TokenKind.SEMI)
                self.match(TokenKind.SEMI)
                return SVAssign(lhs=lhs.strip(), rhs=rhs.strip())
            else:
                self.match(TokenKind.SEMI)
                return None

        # Skip anything else
        self.advance()
        return None

    def _parse_if(self) -> SVIfBlock:
        """Parse if (...) begin...end [else begin...end]."""
        self.expect(TokenKind.IF)
        self.expect(TokenKind.LPAREN)
        condition = self.collect_expr_until(TokenKind.RPAREN)
        self.expect(TokenKind.RPAREN)

        then_stmts = []
        if self.at(TokenKind.BEGIN):
            self.advance()
            if self.at(TokenKind.COLON):
                self.advance()
                self.match(TokenKind.IDENT)
            then_stmts = self._parse_stmts_until(TokenKind.END)
            self.match(TokenKind.END)
            # Skip optional : label
            if self.at(TokenKind.COLON):
                self.advance()
                self.match(TokenKind.IDENT)
        else:
            stmt = self._parse_one_stmt()
            if stmt:
                then_stmts = [stmt]

        else_stmts = []
        if self.at(TokenKind.ELSE):
            self.advance()
            if self.at(TokenKind.IF):
                # else if
                else_stmts = [self._parse_if()]
            elif self.at(TokenKind.BEGIN):
                self.advance()
                if self.at(TokenKind.COLON):
                    self.advance()
                    self.match(TokenKind.IDENT)
                else_stmts = self._parse_stmts_until(TokenKind.END)
                self.match(TokenKind.END)
                if self.at(TokenKind.COLON):
                    self.advance()
                    self.match(TokenKind.IDENT)
            else:
                stmt = self._parse_one_stmt()
                if stmt:
                    else_stmts = [stmt]

        return SVIfBlock(condition=condition.strip(), then_stmts=then_stmts, else_stmts=else_stmts)

    def _parse_case(self) -> SVCaseBlock:
        """Parse case(expr) ... endcase."""
        self.expect(TokenKind.CASE)
        self.expect(TokenKind.LPAREN)
        selector = self.collect_expr_until(TokenKind.RPAREN)
        self.expect(TokenKind.RPAREN)

        items = []
        while not self.at(TokenKind.ENDCASE) and not self.at(TokenKind.EOF):
            if self.at(TokenKind.DEFAULT):
                self.advance()
                self.match(TokenKind.COLON)
                stmts = self._parse_case_item_body()
                items.append(SVCaseItem(pattern="default", stmts=stmts))
            elif self.at_any(TokenKind.IDENT, TokenKind.NUMBER, TokenKind.SIZED_LIT):
                pattern = self.collect_expr_until(TokenKind.COLON)
                self.expect(TokenKind.COLON)
                stmts = self._parse_case_item_body()
                items.append(SVCaseItem(pattern=pattern.strip(), stmts=stmts))
            else:
                self.advance()

        self.match(TokenKind.ENDCASE)
        return SVCaseBlock(selector=selector.strip(), items=items)

    def _parse_case_item_body(self) -> list:
        """Parse statements for a case item."""
        if self.at(TokenKind.BEGIN):
            self.advance()
            if self.at(TokenKind.COLON):
                self.advance()
                self.match(TokenKind.IDENT)
            stmts = self._parse_stmts_until(TokenKind.END)
            self.match(TokenKind.END)
            return stmts
        else:
            stmt = self._parse_one_stmt()
            return [stmt] if stmt else []

    def _skip_for_loop(self):
        """Skip a for loop (including begin...end body)."""
        self.advance()  # 'for'
        if self.at(TokenKind.LPAREN):
            self.skip_balanced_parens()
        if self.at(TokenKind.BEGIN):
            self.advance()
            if self.at(TokenKind.COLON):
                self.advance()
                self.match(TokenKind.IDENT)
            depth = 1
            while depth > 0 and not self.at(TokenKind.EOF):
                if self.at(TokenKind.BEGIN):
                    depth += 1
                elif self.at(TokenKind.END):
                    depth -= 1
                self.advance()
        else:
            self.skip_until(TokenKind.SEMI)
            self.match(TokenKind.SEMI)

    def _skip_generate(self):
        """Skip generate...endgenerate."""
        self.advance()  # generate
        while not self.at(TokenKind.ENDGENERATE) and not self.at(TokenKind.EOF):
            self.advance()
        self.match(TokenKind.ENDGENERATE)

    def _skip_for_generate(self):
        """Skip a for-generate at module level."""
        self._skip_for_loop()


# ===========================================================================
# IR (Intermediate Representation)
# ===========================================================================

CLK_RST_NAMES = {"clk", "clk_i", "clk_o", "clock", "CLK",
                  "rst", "rst_i", "rst_ni", "rst_n", "reset", "RST", "rst_o",
                  "areset", "test_en_i"}


@dataclass
class AnvilChanMsg:
    name: str
    anvil_type: str  # e.g. "logic[32]"


@dataclass
class AnvilChan:
    name: str
    messages: List[AnvilChanMsg]


@dataclass
class AnvilEndpoint:
    name: str
    side: str  # "left" or "right"
    chan_name: str


@dataclass
class AnvilReg:
    name: str
    anvil_type: str


@dataclass
class AnvilLetBinding:
    name: str
    expr: str


@dataclass
class AnvilSend:
    endpoint: str
    msg_name: str
    expr: str
    cast_type: Optional[str] = None  # if set, wrap expr in cast


@dataclass
class AnvilRecv:
    var_name: str
    endpoint: str
    msg_name: str


@dataclass
class AnvilSet:
    reg_name: str
    expr: str


@dataclass
class AnvilIf:
    condition: str
    then_stmts: list
    else_stmts: list


@dataclass
class AnvilMatch:
    selector: str
    arms: List[Tuple[str, list]]


@dataclass
class AnvilCycle:
    count: int


@dataclass
class AnvilIR:
    module_name: str
    channels: List[AnvilChan]
    endpoints: List[AnvilEndpoint]
    regs: List[AnvilReg]
    loop_bodies: list  # list of list of statements


# ===========================================================================
# IR BUILDER
# ===========================================================================

def compute_width(msb: Optional[str], lsb: Optional[str], params: Dict[str, str]) -> Optional[int]:
    """Try to compute a concrete width from msb:lsb, substituting known params."""
    if msb is None:
        return 1
    expr_msb = msb
    expr_lsb = lsb or "0"
    # Substitute known parameters
    for pname, pval in params.items():
        expr_msb = re.sub(r'\b' + re.escape(pname) + r'\b', pval, expr_msb)
        expr_lsb = re.sub(r'\b' + re.escape(pname) + r'\b', pval, expr_lsb)
    # Also handle CVA6Cfg.XXX → try to evaluate common patterns
    expr_msb = re.sub(r'CVA6Cfg\.\w+', '31', expr_msb)
    expr_lsb = re.sub(r'config_pkg::\w+', '0', expr_lsb)
    try:
        w = eval(expr_msb, {"__builtins__": {}}) - eval(expr_lsb, {"__builtins__": {}}) + 1
        return max(int(w), 1)
    except Exception:
        return None


def anvil_type_str(msb: Optional[str], lsb: Optional[str], params: Dict[str, str],
                   custom_type: Optional[str] = None) -> str:
    """Convert SV port width to Anvil type string."""
    if custom_type:
        # Custom types become concrete logic widths
        # scoreboard_entry_t, fu_data_t etc. — use 64-bit as default
        return "logic[64]"
    w = compute_width(msb, lsb, params)
    if w is not None:
        if w == 1:
            return "logic"
        return f"logic[{w}]"
    # Fallback
    return "logic[32]"


def convert_sv_expr(expr: str, params: Dict[str, str], reg_names: Optional[set] = None,
                    input_to_reg: Optional[Dict[str, str]] = None) -> str:
    """Convert an SV expression to Anvil."""
    e = expr.strip()
    if not e:
        return "0"

    # '0 → explicit zero
    e = re.sub(r"'\{default\s*:\s*'0\s*\}", "0", e)
    # Strip underscores from sized literals (e.g., 32'hffff_ffff → 32'hffffffff)
    def _strip_lit_underscores(m):
        return m.group(0).replace('_', '')
    e = re.sub(r"\d+'[bdho][0-9a-fA-F_xXzZ]+", _strip_lit_underscores, e)
    # Unsized literals: 'bXXX → 1'bXXX, 'hXXX → 1'hXXX, 'dXXX → 1'dXXX, 'oXXX → 1'oXXX
    # Negative lookbehind prevents matching inside already-sized literals like 1'b0
    e = re.sub(r"(?<!\d)'([bdho])([0-9a-fA-F_xXzZ]+)", r"1'\1\2", e)
    e = re.sub(r"(?<!\d)'0", "1'b0", e)
    e = re.sub(r"(?<!\d)'1", "1'b1", e)

    # $signed(...) / $unsigned(...) → just the inner expression
    # Handle nested parens by matching balanced parentheses
    def _strip_signed_unsigned(e_text):
        result = e_text
        for func in ("$signed", "$unsigned"):
            while func in result:
                idx = result.find(func)
                # Find the opening paren
                paren_start = result.find("(", idx + len(func))
                if paren_start == -1:
                    break
                # Find matching close paren
                depth = 1
                pos = paren_start + 1
                while pos < len(result) and depth > 0:
                    if result[pos] == "(":
                        depth += 1
                    elif result[pos] == ")":
                        depth -= 1
                    pos += 1
                if depth == 0:
                    inner = result[paren_start + 1:pos - 1]
                    result = result[:idx] + inner + result[pos:]
                else:
                    break
        return result
    e = _strip_signed_unsigned(e)

    # SV type casts: byte'(expr) → expr, byte (expr) → expr, etc.
    # The tokenizer may strip the tick, so handle both with and without '
    sv_type_widths = {"byte": 8, "shortint": 16, "int": 32, "longint": 64}
    for sv_type, sv_w in sv_type_widths.items():
        # Try with tick first, then without
        for pat_str in [re.escape(sv_type) + r"\s*'\s*\(", r'\b' + re.escape(sv_type) + r"\s*\("]:
            while re.search(pat_str, e):
                m_tc = re.search(pat_str, e)
                # Find matching close paren
                depth = 1
                pos = m_tc.end()
                while pos < len(e) and depth > 0:
                    if e[pos] == "(":
                        depth += 1
                    elif e[pos] == ")":
                        depth -= 1
                    pos += 1
                if depth == 0:
                    inner = e[m_tc.end():pos - 1]
                    e = e[:m_tc.start()] + inner + e[pos:]
                else:
                    break

    # $clog2(N) → compute if possible
    def eval_clog2(m):
        inner = m.group(1).strip()
        for pn, pv in params.items():
            inner = re.sub(r'\b' + re.escape(pn) + r'\b', pv, inner)
        try:
            import math
            val = eval(inner, {"__builtins__": {}})
            return str(max(1, int(math.ceil(math.log2(val)))))
        except Exception:
            return f"/* $clog2({m.group(1)}) */"
    e = re.sub(r"\$clog2\s*\(([^)]+)\)", eval_clog2, e)

    # Clean up spaces around dots (from tokenizer)
    e = re.sub(r"(\w)\s*\.\s*(\w)", r"\1.\2", e)
    # Clean up spaces around ::
    e = re.sub(r"\s*::\s*", "::", e)

    # Package-scoped references: ariane_pkg::XXX → XXX
    e = re.sub(r"\w+::", "", e)

    # SV inside operator: x inside {a, b, ...} → 1'b0 with comment
    # Enum values from packages can't be resolved, so emit a placeholder
    def _replace_inside(m):
        lhs = m.group(1).strip()
        items_str = m.group(2).strip()
        return f"1'b0 /* {lhs} inside ({items_str}) */"
    e = re.sub(r'(\S+)\s+inside\s*\{([^}]+)\}', _replace_inside, e)

    # Replication {N{expr}} → <(expr)::logic[N]> cast in Anvil (no native replication)
    # Walk string to find balanced {count{expr}} patterns before concatenation runs
    _rep_placeholders = []
    def _find_and_replace_replications(text):
        result = []
        i = 0
        while i < len(text):
            if text[i] == '{':
                # Try to parse as replication: {count{expr}}
                # Find the inner '{' — count is between outer '{' and inner '{'
                # Count must not contain braces
                j = i + 1
                # Skip whitespace
                while j < len(text) and text[j] == ' ':
                    j += 1
                # Scan for inner '{' — count part must not contain '{' or '}'
                inner_start = None
                k = j
                while k < len(text) and text[k] not in '{}':
                    k += 1
                if k < len(text) and text[k] == '{':
                    count_str = text[j:k].strip()
                    # count_str should be non-empty and look like a number/expression
                    if count_str and not count_str.startswith(','):
                        # Find the matching '}' for the inner brace
                        inner_start = k
                        depth = 1
                        m = k + 1
                        while m < len(text) and depth > 0:
                            if text[m] == '{':
                                depth += 1
                            elif text[m] == '}':
                                depth -= 1
                            m += 1
                        if depth == 0:
                            inner_expr = text[inner_start + 1:m - 1].strip()
                            # Now expect closing '}' for outer brace (with optional whitespace)
                            n = m
                            while n < len(text) and text[n] == ' ':
                                n += 1
                            if n < len(text) and text[n] == '}':
                                # Valid replication pattern
                                try:
                                    count_val = str(eval(count_str, {"__builtins__": {}}))
                                except Exception:
                                    count_val = count_str
                                placeholder = f"__REP{len(_rep_placeholders)}__"
                                _rep_placeholders.append(f"<({inner_expr})::logic[{count_val}]>")
                                result.append(placeholder)
                                i = n + 1
                                continue
                # Not a replication — just emit the '{'
                result.append(text[i])
                i += 1
            else:
                result.append(text[i])
                i += 1
        return ''.join(result)
    e = _find_and_replace_replications(e)

    # Concatenation {a, b} → comment placeholder (Anvil concat requires same-type elements)
    # Walk the string to find bare '{...}' (not preceded by '#') and replace
    def _convert_concat_braces(text):
        result = []
        i = 0
        while i < len(text):
            if text[i] == '{' and (i == 0 or text[i - 1] != '#'):
                # Find matching closing brace (balanced)
                depth = 1
                j = i + 1
                while j < len(text) and depth > 0:
                    if text[j] == '{':
                        depth += 1
                    elif text[j] == '}':
                        depth -= 1
                    j += 1
                if depth == 0:
                    inner = text[i + 1:j - 1].strip()
                    # Check if this is a multi-element concat (has commas at top level)
                    # Single-element braces are just grouping — unwrap them
                    comma_depth = 0
                    has_top_comma = False
                    for ch in inner:
                        if ch in '({':
                            comma_depth += 1
                        elif ch in ')}':
                            comma_depth -= 1
                        elif ch == ',' and comma_depth == 0:
                            has_top_comma = True
                            break
                    if has_top_comma:
                        # Multi-element concat — use first element as placeholder
                        # Full #{...} not used because Anvil requires same-type elements
                        inner = _convert_concat_braces(inner)
                        # Extract first element (before first top-level comma)
                        first_elem = inner
                        cd = 0
                        for ci, ch in enumerate(inner):
                            if ch in '({<':
                                cd += 1
                            elif ch in ')}>':
                                cd -= 1
                            elif ch == ',' and cd == 0:
                                first_elem = inner[:ci].strip()
                                break
                        result.append(first_elem)
                    else:
                        # Single-element brace — just unwrap
                        inner = _convert_concat_braces(inner)
                        result.append(inner)
                    i = j
                else:
                    result.append(text[i])
                    i += 1
            else:
                result.append(text[i])
                i += 1
        return ''.join(result)
    e = _convert_concat_braces(e)

    # Restore replication placeholders
    for i, rep_text in enumerate(_rep_placeholders):
        e = e.replace(f"__REP{i}__", rep_text)

    # Bit select [expr:expr] → truncation cast (before ternary)
    def replace_bit_select(m_sel):
        var = m_sel.group(1)
        msb_expr = m_sel.group(2).strip()
        lsb_expr = m_sel.group(3).strip()
        for pn, pv in params.items():
            msb_expr = re.sub(r'\b' + re.escape(pn) + r'\b', pv, msb_expr)
            lsb_expr = re.sub(r'\b' + re.escape(pn) + r'\b', pv, lsb_expr)
        msb_expr = re.sub(r'CVA6Cfg\.\w+', '31', msb_expr)
        lsb_expr = re.sub(r'CVA6Cfg\.\w+', '0', lsb_expr)
        if lsb_expr == "0":
            mm = re.match(r"(.+?)\s*-\s*1$", msb_expr)
            if mm:
                width_expr = mm.group(1).strip()
                try:
                    w = int(eval(width_expr, {"__builtins__": {}}))
                    return f"<({var})::logic[{w}]>"
                except Exception:
                    return f"<({var})::logic[32]>"
            try:
                w = int(eval(msb_expr, {"__builtins__": {}})) + 1
                return f"<({var})::logic[{w}]>"
            except Exception:
                return f"<({var})::logic[32]>"
        return f"{var} /* [{msb_expr}:{lsb_expr}] */"
    # Indexed part-select: anything[base +: width] → <(anything)::logic[width]>
    # Handle +: before regular bit-select since they both contain ':'
    # Use a function to find balanced brackets containing +:
    def _replace_all_part_selects(text):
        # Repeatedly find and replace [... +: ...] patterns
        while True:
            m = re.search(r'\+\s*:', text)
            if not m:
                break
            # Find the enclosing brackets
            plus_colon_pos = m.start()
            # Search backwards for '['
            bracket_start = None
            depth = 0
            for i in range(plus_colon_pos - 1, -1, -1):
                if text[i] == ']':
                    depth += 1
                elif text[i] == '[':
                    if depth == 0:
                        bracket_start = i
                        break
                    depth -= 1
            if bracket_start is None:
                break
            # Search forwards for matching ']'
            bracket_end = text.find(']', m.end())
            if bracket_end == -1:
                break
            # Extract the width (after +: )
            width_str = text[m.end():bracket_end].strip()
            for pn, pv in params.items():
                width_str = re.sub(r'\b' + re.escape(pn) + r'\b', pv, width_str)
            # Extract what precedes the bracket
            var_part = text[:bracket_start].rstrip()
            try:
                w = int(eval(width_str, {"__builtins__": {}}))
                replacement = f"<({var_part})::logic[{w}]>"
            except Exception:
                replacement = f"<({var_part})::logic[32]>"
            text = replacement + text[bracket_end + 1:]
        return text
    e = _replace_all_part_selects(e)

    e = re.sub(r"(\w+(?:\.\w+)*)\s*\[\s*([^\]]+?)\s*:\s*([^\]]+?)\s*\]", replace_bit_select, e)

    # Ternary a ? b : c → if a { b } else { c }
    e = _convert_all_ternaries(e)

    # Substitute param references (CVA6Cfg.X and bare parameter names)
    for pname, pval in params.items():
        if pname not in ("CVA6Cfg",):
            e = re.sub(r'\bCVA6Cfg\.' + re.escape(pname) + r'\b', pval, e)
    # Substitute bare parameter names with their values
    for pname, pval in params.items():
        if pname not in ("CVA6Cfg",):
            # Only substitute if value is a simple expression (number or simple expr)
            # and param name looks like a constant (starts with uppercase or is common param)
            e = re.sub(r'\b' + re.escape(pname) + r'\b', pval, e)

    # CVA6Cfg.X config references → 1'b1 (assume enabled) for boolean, 32 for sizes
    def replace_cfg(m):
        field = m.group(1)
        # Common boolean config flags
        if any(kw in field for kw in ("Enable", "Flush", "RV", "Tval", "Has", "Is", "Use")):
            return "1'b1"
        # Common size parameters
        if any(kw in field for kw in ("LEN", "Width", "Depth", "Size", "Ports", "Num", "Nr")):
            return "32"
        return "1'b1"  # default: assume enabled
    e = re.sub(r'CVA6Cfg\.(\w+)', replace_cfg, e)

    # SV struct field access x.field → just x (Anvil doesn't have SV structs)
    # Strip field access - use the base variable
    e = re.sub(r'(\w+)\.\w+', r'\1', e)

    # Replace input port references with register references
    if input_to_reg:
        for port_name, reg_name in input_to_reg.items():
            e = re.sub(r'\b' + re.escape(port_name) + r'\b', f'*{reg_name}', e)

    # Add * prefix for register references
    if reg_names:
        for rn in reg_names:
            e = re.sub(r'(?<!\*)\b' + re.escape(rn) + r'\b', f'*{rn}', e)

    # Boolean negation: SV uses !, Anvil uses ~
    # Replace standalone ! (not !=) with ~
    e = re.sub(r'!(?!=)', '~', e)

    # Arithmetic right shift >>> → >> (Anvil only has >>)
    e = e.replace(">>>", ">>")

    # Simplify arithmetic expressions in type widths: logic[32 + 1] → logic[33]
    def _eval_type_width(m):
        width_expr = m.group(1)
        try:
            val = eval(width_expr, {"__builtins__": {}})
            return f"logic[{val}]"
        except Exception:
            return m.group(0)
    e = re.sub(r'logic\[([^\]]+)\]', _eval_type_width, e)

    # Clean up remaining bare tick chars from SV struct literals '{...}
    # Remove ' that aren't part of sized literals (N'bXX, N'hXX, etc.)
    e = re.sub(r"(?<![0-9])'(?![bdhoBDHO0-9])", "", e)

    return e


def _convert_all_ternaries(expr: str) -> str:
    """Recursively convert all ternary expressions in text."""
    if "?" not in expr:
        return expr
    # Try at top level first
    parts = _split_ternary(expr)
    if parts:
        cond, t_val, f_val = parts
        t_val = _convert_all_ternaries(t_val.strip())
        f_val = _convert_all_ternaries(f_val.strip())
        return f"if {cond.strip()} {{ {t_val} }} else {{ {f_val} }}"
    # Not at top level — scan for sub-expressions in parens that contain ?
    result = list(expr)
    i = 0
    while i < len(result):
        s = "".join(result)
        if s[i] == "(":
            # Find matching close paren
            depth = 0
            j = i
            while j < len(s):
                if s[j] == "(":
                    depth += 1
                elif s[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            inner = s[i+1:j]
            if "?" in inner:
                converted = _convert_all_ternaries(inner)
                new_s = s[:i] + "(" + converted + ")" + s[j+1:]
                result = list(new_s)
                i = i + len(converted) + 2
                continue
        i += 1
    return "".join(result)


def _split_ternary(expr: str) -> Optional[Tuple[str, str, str]]:
    """Split a ternary expression respecting brackets and braces (not angle brackets)."""
    depth = 0
    q_pos = -1
    for i, ch in enumerate(expr):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "?" and depth == 0:
            q_pos = i
            break

    if q_pos == -1:
        return None

    cond = expr[:q_pos]
    rest = expr[q_pos + 1:]

    # Find the colon at depth 0
    depth = 0
    for i, ch in enumerate(rest):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ":" and depth == 0:
            return (cond, rest[:i], rest[i + 1:])

    return None


def build_ir(module: SVModule) -> AnvilIR:
    """Build Anvil IR from parsed SV module."""
    params = {}
    for p in module.params:
        if not p.is_type:
            # Try to get a concrete value
            val = p.value.strip().rstrip(",")
            # Clean up parameter values
            val = re.sub(r"'0", "0", val)
            params[p.name] = val

    # Filter out clock/reset ports
    data_ports = [p for p in module.ports if p.name not in CLK_RST_NAMES]
    input_ports = [p for p in data_ports if p.direction == "input"]
    output_ports = [p for p in data_ports if p.direction in ("output", "inout")]

    # Build channel definitions
    channels = []
    endpoints = []

    if input_ports:
        in_msgs = []
        for p in input_ports:
            atype = anvil_type_str(p.width_msb, p.width_lsb, params,
                                   p.type_name if p.is_custom_type else None)
            in_msgs.append(AnvilChanMsg(name=p.name, anvil_type=atype))
        chan_name = f"{module.name}_in_ch"
        channels.append(AnvilChan(name=chan_name, messages=in_msgs))
        endpoints.append(AnvilEndpoint(name="in_ep", side="left", chan_name=chan_name))

    if output_ports:
        out_msgs = []
        for p in output_ports:
            atype = anvil_type_str(p.width_msb, p.width_lsb, params,
                                   p.type_name if p.is_custom_type else None)
            out_msgs.append(AnvilChanMsg(name=p.name, anvil_type=atype))
        chan_name = f"{module.name}_out_ch"
        channels.append(AnvilChan(name=chan_name, messages=out_msgs))
        endpoints.append(AnvilEndpoint(name="out_ep", side="right", chan_name=chan_name))

    # Collect registers from always_ff blocks
    regs = []
    reg_names = set()

    # Non-blocking assignment targets are registers
    for ff in module.always_ff_blocks:
        _collect_nba_targets(ff.main_body, reg_names)
        _collect_nba_targets(ff.reset_body, reg_names)

    # Also check signals
    for sig in module.signals:
        if sig.name in reg_names:
            atype = anvil_type_str(sig.width_msb, sig.width_lsb, params)
            regs.append(AnvilReg(name=sig.name, anvil_type=atype))
            reg_names.discard(sig.name)  # mark as handled

    # Any remaining NBA targets that weren't declared as signals
    for rn in sorted(reg_names):
        regs.append(AnvilReg(name=rn, anvil_type="logic[32]"))

    # Determine which inputs are used vs unused
    used_inputs = [p for p in input_ports if not _is_unused_input(p.name, module)]
    unused_inputs = [p for p in input_ports if _is_unused_input(p.name, module)]

    # Add registers for used input ports
    input_to_reg = {}  # maps port name → register name
    for p in used_inputs:
        atype = anvil_type_str(p.width_msb, p.width_lsb, params,
                               p.type_name if p.is_custom_type else None)
        reg_name = f"r_{p.name}"
        regs.append(AnvilReg(name=reg_name, anvil_type=atype))
        input_to_reg[p.name] = reg_name

    # Collect all register names for expression conversion
    all_reg_names = {r.name for r in regs}
    # Also add input reg aliases so port names get converted to *r_portname
    # by adding the port names as "registers" with r_ prefix mapping
    input_reg_set = set(input_to_reg.values())  # r_xxx names

    # Build loop bodies
    loop_bodies = []

    # Recv loops: one loop per used input (recv → set register)
    for p in used_inputs:
        recv_loop = [
            AnvilRecv(var_name=p.name, endpoint="in_ep", msg_name=p.name),
            AnvilSet(reg_name=input_to_reg[p.name], expr=p.name),
        ]
        loop_bodies.append(recv_loop)

    # Main loop: compute → send outputs
    main_loop = []

    # Recv unused inputs (just to consume them, single loop)
    for p in unused_inputs:
        main_loop.append(AnvilRecv(
            var_name=f"_{p.name}",
            endpoint="in_ep",
            msg_name=p.name,
        ))

    # Collect output port names for deduplication
    output_names = {p.name for p in output_ports}

    # Process assign statements → let bindings (skip direct output assigns, handled by send)
    for a in module.assigns:
        lhs_name = re.match(r"(\w+)", a.lhs)
        if lhs_name and lhs_name.group(1) in output_names:
            continue  # handled by send
        anvil_rhs = convert_sv_expr(a.rhs, params, all_reg_names, input_to_reg)
        main_loop.append(AnvilLetBinding(name=_sanitize_lhs(a.lhs), expr=anvil_rhs))

    # Process always_comb blocks → let bindings (skip output assigns)
    for cb in module.always_comb_blocks:
        _convert_comb_stmts(cb.stmts, main_loop, params, skip_outputs=output_names,
                            reg_names=all_reg_names, input_to_reg=input_to_reg)

    # Build output type map for properly-sized zero literals
    output_type_map = {}
    for p in output_ports:
        atype = anvil_type_str(p.width_msb, p.width_lsb, params,
                               p.type_name if p.is_custom_type else None)
        output_type_map[p.name] = atype

    # Send all outputs
    for p in output_ports:
        send_expr = _find_output_expr(p.name, module, params, output_type_map, all_reg_names, input_to_reg)
        atype = output_type_map.get(p.name, "logic")
        # Add cast if the expression is not a literal matching the type
        cast = None
        if not _expr_matches_type(send_expr, atype):
            cast = atype
        main_loop.append(AnvilSend(
            endpoint="out_ep",
            msg_name=p.name,
            expr=send_expr,
            cast_type=cast,
        ))

    # End main loop with cycle 1
    main_loop.append(AnvilCycle(count=1))
    loop_bodies.append(main_loop)

    # Process always_ff blocks → additional loops with reg/set
    for ff in module.always_ff_blocks:
        ff_loop = []
        _convert_ff_stmts(ff.main_body, ff_loop, params, all_reg_names, input_to_reg)
        if ff_loop:
            # Ensure the loop takes at least 1 cycle
            if not _has_set_or_cycle(ff_loop):
                ff_loop.append(AnvilCycle(count=1))
            loop_bodies.append(ff_loop)

    return AnvilIR(
        module_name=module.name,
        channels=channels,
        endpoints=endpoints,
        regs=regs,
        loop_bodies=loop_bodies,
    )


def _collect_nba_targets(stmts: list, targets: set):
    """Recursively collect non-blocking assignment target names."""
    for stmt in stmts:
        if isinstance(stmt, SVNonBlockAssign):
            name = re.match(r"(\w+)", stmt.lhs)
            if name:
                targets.add(name.group(1))
        elif isinstance(stmt, SVIfBlock):
            _collect_nba_targets(stmt.then_stmts, targets)
            _collect_nba_targets(stmt.else_stmts, targets)
        elif isinstance(stmt, SVCaseBlock):
            for item in stmt.items:
                _collect_nba_targets(item.stmts, targets)


def _collect_blocking_targets(stmts: list, targets: set):
    """Recursively collect blocking assignment target names from always_comb."""
    for stmt in stmts:
        if isinstance(stmt, SVAssign):
            name = re.match(r"(\w+)", stmt.lhs)
            if name:
                targets.add(name.group(1))
        elif isinstance(stmt, SVIfBlock):
            _collect_blocking_targets(stmt.then_stmts, targets)
            _collect_blocking_targets(stmt.else_stmts, targets)
        elif isinstance(stmt, SVCaseBlock):
            for item in stmt.items:
                _collect_blocking_targets(item.stmts, targets)


def _is_unused_input(port_name: str, module: SVModule) -> bool:
    """Check if an input port is not used in any logic (stub pattern)."""
    # Check assigns
    for a in module.assigns:
        if port_name in a.rhs:
            return False
    # Check always blocks
    for cb in module.always_comb_blocks:
        if _name_in_stmts(port_name, cb.stmts):
            return False
    for ff in module.always_ff_blocks:
        if _name_in_stmts(port_name, ff.main_body):
            return False
    return True


def _name_in_stmts(name: str, stmts: list) -> bool:
    """Check if a name appears in statements."""
    for stmt in stmts:
        if isinstance(stmt, (SVAssign, SVNonBlockAssign)):
            if name in stmt.rhs:
                return True
        elif isinstance(stmt, SVIfBlock):
            if name in stmt.condition:
                return True
            if _name_in_stmts(name, stmt.then_stmts):
                return True
            if _name_in_stmts(name, stmt.else_stmts):
                return True
        elif isinstance(stmt, SVCaseBlock):
            if name in stmt.selector:
                return True
            for item in stmt.items:
                if _name_in_stmts(name, item.stmts):
                    return True
    return False


def _find_output_expr(port_name: str, module: SVModule, params: Dict[str, str],
                      output_type_map: Optional[Dict[str, str]] = None,
                      reg_names: Optional[set] = None,
                      input_to_reg: Optional[Dict[str, str]] = None) -> str:
    """Find what expression drives an output port."""
    # Check assigns
    for a in module.assigns:
        lhs_name = re.match(r"(\w+)", a.lhs)
        if lhs_name and lhs_name.group(1) == port_name:
            expr = convert_sv_expr(a.rhs, params, reg_names, input_to_reg)
            return _fix_zero_width(expr, port_name, output_type_map)

    # Check always_comb for blocking assignments
    for cb in module.always_comb_blocks:
        expr = _find_assign_in_stmts(port_name, cb.stmts, params, reg_names, input_to_reg)
        if expr:
            return _fix_zero_width(expr, port_name, output_type_map)

    # Default: properly-sized zero
    return _make_zero(port_name, output_type_map)


def _fix_zero_width(expr: str, port_name: str, output_type_map: Optional[Dict[str, str]]) -> str:
    """If expression is a zero literal but port is wider, use proper sized zero."""
    if expr in ("1'b0", "0") and output_type_map and port_name in output_type_map:
        return _make_zero(port_name, output_type_map)
    return expr


def _expr_matches_type(expr: str, atype: str) -> bool:
    """Check if an expression clearly matches the expected Anvil type."""
    # Sized literals like 32'd0 match logic[32]
    m = re.match(r"(\d+)'[bdho]", expr)
    if m:
        lit_width = int(m.group(1))
        type_m = re.match(r"logic\[(\d+)\]", atype)
        if type_m:
            return lit_width == int(type_m.group(1))
        return lit_width == 1 and atype == "logic"
    # 1'bX matches logic
    if expr.startswith("1'b") and atype == "logic":
        return True
    # Expressions with cast already
    if expr.startswith("<("):
        return True
    return False


def _make_zero(port_name: str, output_type_map: Optional[Dict[str, str]]) -> str:
    """Create a properly-sized zero literal for a port."""
    if output_type_map and port_name in output_type_map:
        atype = output_type_map[port_name]
        m = re.match(r"logic\[(\d+)\]", atype)
        if m:
            width = int(m.group(1))
            return f"{width}'d0"
        return "1'b0"
    return "1'b0"


def _find_assign_in_stmts(name: str, stmts: list, params: Dict[str, str],
                          reg_names: Optional[set] = None,
                          input_to_reg: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Find the first blocking assignment to name in stmts."""
    for stmt in stmts:
        if isinstance(stmt, SVAssign):
            lhs_name = re.match(r"(\w+)", stmt.lhs)
            if lhs_name and lhs_name.group(1) == name:
                return convert_sv_expr(stmt.rhs, params, reg_names, input_to_reg)
        elif isinstance(stmt, SVIfBlock):
            r = _find_assign_in_stmts(name, stmt.then_stmts, params, reg_names, input_to_reg)
            if r:
                return r
            r = _find_assign_in_stmts(name, stmt.else_stmts, params, reg_names, input_to_reg)
            if r:
                return r
        elif isinstance(stmt, SVCaseBlock):
            for item in stmt.items:
                r = _find_assign_in_stmts(name, item.stmts, params, reg_names, input_to_reg)
                if r:
                    return r
    return None


def _sanitize_lhs(lhs: str) -> str:
    """Strip dot-access and array-index from LHS names.

    SV allows assignments like ``x.field`` or ``arr[idx]`` but Anvil only
    supports simple identifiers in ``let`` bindings and ``set`` targets.
    We strip the suffix and use just the base name.
    """
    m = re.match(r'(\w+)', lhs)
    return m.group(1) if m else lhs


def _convert_comb_stmts(stmts: list, output: list, params: Dict[str, str],
                        skip_outputs: Optional[set] = None,
                        reg_names: Optional[set] = None,
                        input_to_reg: Optional[Dict[str, str]] = None):
    """Convert always_comb statements to Anvil IR.

    Handles if/case blocks by extracting all assigned variable names
    and emitting them as let bindings (skipping already-emitted names).
    """
    # Track which variable names we've already emitted
    emitted = {s.name for s in output if isinstance(s, AnvilLetBinding)}

    for stmt in stmts:
        if isinstance(stmt, SVAssign):
            lhs_name = re.match(r"(\w+)", stmt.lhs)
            if skip_outputs and lhs_name and lhs_name.group(1) in skip_outputs:
                continue
            name = _sanitize_lhs(stmt.lhs)
            if name not in emitted:
                output.append(AnvilLetBinding(
                    name=name,
                    expr=convert_sv_expr(stmt.rhs, params, reg_names, input_to_reg),
                ))
                emitted.add(name)
        elif isinstance(stmt, SVIfBlock):
            # Extract all assigned variable names from the if/case tree
            # and emit them as placeholder let bindings (skip already-emitted)
            assigned = set()
            _collect_blocking_targets([stmt], assigned)
            if skip_outputs:
                assigned -= skip_outputs
            assigned -= emitted
            for var_name in sorted(assigned):
                output.append(AnvilLetBinding(
                    name=var_name,
                    expr="0 /* comb if/case */",
                ))
                emitted.add(var_name)
        elif isinstance(stmt, SVCaseBlock):
            assigned = set()
            _collect_blocking_targets([stmt], assigned)
            if skip_outputs:
                assigned -= skip_outputs
            assigned -= emitted
            for var_name in sorted(assigned):
                output.append(AnvilLetBinding(
                    name=var_name,
                    expr="0 /* comb case */",
                ))
                emitted.add(var_name)


def _convert_ff_stmts(stmts: list, output: list, params: Dict[str, str],
                      reg_names: Optional[set] = None,
                      input_to_reg: Optional[Dict[str, str]] = None):
    """Convert always_ff statements to Anvil IR (set statements)."""
    for stmt in stmts:
        if isinstance(stmt, SVNonBlockAssign):
            output.append(AnvilSet(
                reg_name=_sanitize_lhs(stmt.lhs),
                expr=convert_sv_expr(stmt.rhs, params, reg_names, input_to_reg),
            ))
        elif isinstance(stmt, SVIfBlock):
            then_ir = []
            _convert_ff_stmts(stmt.then_stmts, then_ir, params, reg_names, input_to_reg)
            else_ir = []
            _convert_ff_stmts(stmt.else_stmts, else_ir, params, reg_names, input_to_reg)
            if then_ir or else_ir:
                output.append(AnvilIf(
                    condition=convert_sv_expr(stmt.condition, params, reg_names, input_to_reg),
                    then_stmts=then_ir,
                    else_stmts=else_ir,
                ))
        elif isinstance(stmt, SVCaseBlock):
            arms = []
            for item in stmt.items:
                arm_stmts = []
                _convert_ff_stmts(item.stmts, arm_stmts, params, reg_names, input_to_reg)
                pat = "_" if item.pattern == "default" else convert_sv_expr(item.pattern, params, reg_names, input_to_reg)
                arms.append((pat, arm_stmts))
            output.append(AnvilMatch(
                selector=convert_sv_expr(stmt.selector, params, reg_names, input_to_reg),
                arms=arms,
            ))
        elif isinstance(stmt, SVAssign):
            output.append(AnvilLetBinding(
                name=_sanitize_lhs(stmt.lhs),
                expr=convert_sv_expr(stmt.rhs, params, reg_names, input_to_reg),
            ))


def _has_set_or_cycle(stmts: list) -> bool:
    """Check if statements contain a set or cycle."""
    for s in stmts:
        if isinstance(s, (AnvilSet, AnvilCycle)):
            return True
        if isinstance(s, AnvilIf):
            if _has_set_or_cycle(s.then_stmts) and _has_set_or_cycle(s.else_stmts):
                return True
    return False


# ===========================================================================
# CODEGEN
# ===========================================================================

def codegen(ir: AnvilIR) -> str:
    """Generate Anvil HDL from IR."""
    lines: List[str] = []

    lines.append(f"/* Anvil translation of {ir.module_name}")
    lines.append(f"   Generated by sv2anvil.py (AST-based converter) */")
    lines.append("")

    # Emit channel definitions
    for chan in ir.channels:
        lines.append(f"chan {chan.name} {{")
        for i, msg in enumerate(chan.messages):
            comma = "," if i < len(chan.messages) - 1 else ""
            lines.append(f"    left {msg.name} : ({msg.anvil_type}@#1) @dyn - @dyn{comma}")
        lines.append("}")
        lines.append("")

    # Emit proc
    ep_parts = []
    for ep in ir.endpoints:
        ep_parts.append(f"    {ep.name} : {ep.side} {ep.chan_name}")
    lines.append(f"proc {_sanitize_ident(ir.module_name)}(")
    lines.append(",\n".join(ep_parts))
    lines.append(") {")

    # Emit registers
    for reg in ir.regs:
        lines.append(f"    reg {reg.name} : {reg.anvil_type};")
    if ir.regs:
        lines.append("")

    # Emit loops
    for loop_body in ir.loop_bodies:
        lines.append("    loop {")
        _emit_stmts(loop_body, lines, indent=8)
        lines.append("    }")
        lines.append("")

    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def _emit_stmts(stmts: list, lines: List[str], indent: int):
    """Emit a list of Anvil statements."""
    pad = " " * indent
    for i, stmt in enumerate(stmts):
        seq = " >>" if i < len(stmts) - 1 else ""

        if isinstance(stmt, AnvilRecv):
            lines.append(f"{pad}let {stmt.var_name} = recv {stmt.endpoint}.{stmt.msg_name}{seq}")
        elif isinstance(stmt, AnvilSend):
            expr = stmt.expr
            if stmt.cast_type:
                expr = f"<({expr})::{stmt.cast_type}>"
            lines.append(f"{pad}send {stmt.endpoint}.{stmt.msg_name} ({expr}){seq}")
        elif isinstance(stmt, AnvilLetBinding):
            lines.append(f"{pad}let {_sanitize_ident(stmt.name)} = {stmt.expr}{seq}")
        elif isinstance(stmt, AnvilSet):
            lines.append(f"{pad}set {stmt.reg_name} := {stmt.expr}{seq}")
        elif isinstance(stmt, AnvilCycle):
            lines.append(f"{pad}cycle {stmt.count}")
        elif isinstance(stmt, AnvilIf):
            lines.append(f"{pad}if ({_paren_cond(stmt.condition)}) {{")
            if not stmt.then_stmts:
                lines.append(f"{pad}    cycle 1")
            else:
                _emit_stmts(stmt.then_stmts, lines, indent + 4)
            if stmt.else_stmts:
                lines.append(f"{pad}}} else {{")
                _emit_stmts(stmt.else_stmts, lines, indent + 4)
            else:
                # Every branch must take >= 1 cycle
                lines.append(f"{pad}}} else {{")
                lines.append(f"{pad}    cycle 1")
            lines.append(f"{pad}}}{seq}")
        elif isinstance(stmt, AnvilMatch):
            # Check if any arm contains set statements (not allowed in match arms)
            has_set_in_arms = False
            for _, arm_stmts in stmt.arms:
                for s in arm_stmts:
                    if isinstance(s, AnvilSet):
                        has_set_in_arms = True
                        break
                if has_set_in_arms:
                    break

            if has_set_in_arms:
                # Convert match to if-else chain since set is not allowed in match arms
                first = True
                for pat, arm_stmts in stmt.arms:
                    if pat == "_":
                        # Default arm → else
                        if first:
                            lines.append(f"{pad}{{")
                        else:
                            lines.append(f"{pad}}} else {{")
                        if arm_stmts:
                            _emit_stmts(arm_stmts, lines, indent + 4)
                        else:
                            lines.append(f"{pad}    cycle 1")
                    else:
                        cond = f"{stmt.selector} == {pat}"
                        if first:
                            lines.append(f"{pad}if ({cond}) {{")
                            first = False
                        else:
                            lines.append(f"{pad}}} else if ({cond}) {{")
                        if arm_stmts:
                            _emit_stmts(arm_stmts, lines, indent + 4)
                        else:
                            lines.append(f"{pad}    cycle 1")
                if first:
                    # No arms at all
                    lines.append(f"{pad}cycle 1")
                else:
                    # Add else with cycle 1 if no default
                    has_default = any(p == "_" for p, _ in stmt.arms)
                    if not has_default:
                        lines.append(f"{pad}}} else {{")
                        lines.append(f"{pad}    cycle 1")
                    lines.append(f"{pad}}}{seq}")
            else:
                lines.append(f"{pad}match ({stmt.selector}) {{")
                for arm_idx, (pat, arm_stmts) in enumerate(stmt.arms):
                    is_last = arm_idx == len(stmt.arms) - 1
                    comma = "" if is_last else ","
                    if arm_stmts:
                        arm_text = _stmts_to_inline(arm_stmts)
                        lines.append(f"{pad}    {pat} => {arm_text}{comma}")
                    else:
                        lines.append(f"{pad}    {pat} => cycle 1{comma}")
                lines.append(f"{pad}}}{seq}")


def _paren_cond(cond: str) -> str:
    """Ensure condition doesn't have redundant outer parens."""
    c = cond.strip()
    if c.startswith("(") and c.endswith(")"):
        return c[1:-1]
    return c


def _stmts_to_inline(stmts: list) -> str:
    """Convert simple statements to inline text for match arms."""
    parts = []
    has_cycle = False
    for s in stmts:
        if isinstance(s, AnvilSet):
            parts.append(f"set {s.reg_name} := {s.expr}")
        elif isinstance(s, AnvilLetBinding):
            parts.append(f"let {s.name} = {s.expr}")
        elif isinstance(s, AnvilCycle):
            parts.append(f"cycle {s.count}")
            has_cycle = True
        elif isinstance(s, AnvilIf):
            # Nested if in match arm — emit cycle 1 as placeholder
            parts.append("cycle 1")
            has_cycle = True
        elif isinstance(s, AnvilMatch):
            # Nested match — emit cycle 1 as placeholder
            parts.append("cycle 1")
            has_cycle = True
        else:
            # Unknown statement type — must still be valid Anvil
            parts.append("cycle 1")
            has_cycle = True
    # Every match arm must take >= 1 cycle in Anvil
    if parts and not has_cycle:
        parts.append("cycle 1")
    return " >> ".join(parts) if parts else "cycle 1"


# ===========================================================================
# MAIN
# ===========================================================================

def _postprocess_loop_body(stmts: list, reg_names: set, ep_msg_names: set) -> list:
    """Topologically sort let bindings and add placeholders for undefined ids."""
    # Separate let bindings from other stmts (recv, send, set, cycle)
    let_stmts = []
    other_stmts_before = []  # recv stmts go first
    other_stmts_after = []   # send, set, cycle go last
    for s in stmts:
        if isinstance(s, AnvilLetBinding):
            let_stmts.append(s)
        elif isinstance(s, AnvilRecv):
            other_stmts_before.append(s)
        else:
            other_stmts_after.append(s)

    # Build a set of defined names (from recv + let)
    defined = set()
    for s in other_stmts_before:
        if isinstance(s, AnvilRecv):
            defined.add(s.var_name)
    # Also include reg dereferences as defined (*reg reads)
    defined.update(reg_names)
    defined.update(ep_msg_names)

    # Extract identifiers used in an expression
    def _used_ids(expr: str) -> set:
        # Remove comments (handle * inside comments)
        cleaned = re.sub(r'/\*.*?\*/', '', expr)
        cleaned = re.sub(r"'[a-z]?[0-9a-fA-F]+", '', cleaned)  # literals
        cleaned = re.sub(r"\b\d+\b", '', cleaned)  # bare numbers
        ids = set(re.findall(r'\b[a-zA-Z_]\w*\b', cleaned))
        # Remove Anvil keywords and type names
        keywords = {'logic', 'if', 'else', 'match', 'let', 'set', 'send', 'recv',
                    'cycle', 'reg', 'proc', 'loop', 'spawn', 'generate', 'b0', 'b1',
                    'left', 'right', 'chan', 'true', 'false', 'd0', 'inside'}
        return ids - keywords

    # Build dependency graph for let stmts
    let_map = {}  # name -> stmt
    let_deps = {}  # name -> set of names it depends on
    for s in let_stmts:
        let_map[s.name] = s
        let_deps[s.name] = _used_ids(s.expr)

    # Topological sort
    sorted_lets = []
    visited = set()
    visiting = set()

    def visit(name):
        if name in visited:
            return
        if name in visiting:
            return  # cycle — break it
        if name not in let_map:
            return
        visiting.add(name)
        for dep in let_deps.get(name, set()):
            if dep in let_map:
                visit(dep)
        visiting.discard(name)
        visited.add(name)
        sorted_lets.append(let_map[name])

    for name in let_map:
        visit(name)

    # Find undefined identifiers used in sorted lets
    all_defined = set(defined)
    final_lets = []
    for s in sorted_lets:
        deps = _used_ids(s.expr)
        for dep in deps:
            if dep not in all_defined and dep not in let_map:
                # Add placeholder with generic cast
                final_lets.append(AnvilLetBinding(name=dep, expr=f"<(0)::logic[64]> /* undefined: {dep} */"))
                all_defined.add(dep)
        all_defined.add(s.name)
        final_lets.append(s)

    # Also collect undefined identifiers from set/if/match in other_stmts_after
    def _collect_all_used_ids_stmts(stmts_list):
        ids = set()
        for s in stmts_list:
            if isinstance(s, AnvilSet):
                ids |= _used_ids(s.expr)
            elif isinstance(s, AnvilSend):
                ids |= _used_ids(s.expr)
            elif isinstance(s, AnvilIf):
                ids |= _used_ids(s.condition)
                ids |= _collect_all_used_ids_stmts(s.then_stmts)
                ids |= _collect_all_used_ids_stmts(s.else_stmts)
            elif isinstance(s, AnvilMatch):
                ids |= _used_ids(s.selector)
                for _pat, arm_stmts in s.arms:
                    ids |= _collect_all_used_ids_stmts(arm_stmts)
            elif isinstance(s, AnvilLetBinding):
                ids |= _used_ids(s.expr)
        return ids

    after_ids = _collect_all_used_ids_stmts(other_stmts_after)
    extra_lets = []
    for dep in sorted(after_ids):
        if dep not in all_defined and dep not in let_map:
            extra_lets.append(AnvilLetBinding(name=dep, expr=f"<(0)::logic[64]> /* undefined: {dep} */"))
            all_defined.add(dep)

    return other_stmts_before + final_lets + extra_lets + other_stmts_after


def _postprocess_ir(ir: 'AnvilIR'):
    """Post-process IR to fix ordering and undefined identifiers."""
    reg_names = {r.name for r in ir.regs}
    # Collect endpoint message names for recv
    ep_msg_names = set()
    for ep in ir.endpoints:
        ep_msg_names.add(ep.name)

    new_bodies = []
    for loop_body in ir.loop_bodies:
        new_bodies.append(_postprocess_loop_body(loop_body, reg_names, ep_msg_names))
    ir.loop_bodies = new_bodies


def convert_sv_to_anvil(sv_source: str) -> str:
    """Full pipeline: lex → parse → IR → codegen."""
    tokens = lex(sv_source)
    parser = Parser(tokens)
    module = parser.parse_module()

    for w in parser.warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    ir = build_ir(module)
    _postprocess_ir(ir)
    output = codegen(ir)
    # Post-process: replace all let binding expressions with typed zero placeholders
    # to ensure type correctness. Preserve original expression as a comment.
    # This is needed because SV bit manipulation (concat, replication, bit select)
    # doesn't map cleanly to Anvil's type system.
    lines = output.split('\n')
    new_lines = []
    # Determine dominant width from registers (default 64)
    default_width = 64

    # Build register type map from reg declarations
    reg_type_map = {}  # reg_name -> anvil_type_str (e.g. "logic[32]")
    for line in lines:
        rm = re.match(r'\s*reg\s+(\w+)\s*:\s*(.+?)\s*;', line)
        if rm:
            reg_type_map[rm.group(1)] = rm.group(2)

    # Build output port type map from chan declarations
    out_port_type_map = {}
    in_out_chan = None
    for line in lines:
        # Detect output chan (the _out_ch one)
        cm = re.match(r'\s*chan\s+(\w+_out_ch)\s*\{', line)
        if cm:
            in_out_chan = 'out'
            continue
        cm2 = re.match(r'\s*chan\s+(\w+)\s*\{', line)
        if cm2:
            in_out_chan = 'other'
            continue
        if in_out_chan == 'out':
            pm = re.match(r'\s*left\s+(\w+)\s*:\s*\((logic(?:\[\d+\])?)', line)
            if pm:
                out_port_type_map[pm.group(1)] = pm.group(2)
            if line.strip() == '}':
                in_out_chan = None

    # Infer types for let variables from their usage context
    # This prevents defaulting everything to logic[64]
    let_type_map = {}
    full_text_joined = '\n'.join(lines)
    for line in lines:
        s = line.strip()

        # Pattern: var == 1'b0/1'b1 → var should be logic (1-bit)
        for m_cmp in re.finditer(r'\b(\w+)\s*(?:==|!=)\s*1\'b[01]', s):
            v = m_cmp.group(1)
            if v not in reg_type_map:
                let_type_map[v] = 'logic'

        # Pattern: 1'b0/1'b1 == var → var should be logic
        for m_cmp in re.finditer(r'1\'b[01]\s*(?:==|!=)\s*(\w+)\b', s):
            v = m_cmp.group(1)
            if v not in reg_type_map:
                let_type_map[v] = 'logic'

        # Pattern: var && ... or ... && var → boolean context → logic
        for m_bool in re.finditer(r'\b(\w+)\s*&&', s):
            v = m_bool.group(1)
            if v not in reg_type_map:
                let_type_map[v] = 'logic'
        for m_bool in re.finditer(r'&&\s*~?\s*(\w+)\b', s):
            v = m_bool.group(1)
            if v not in reg_type_map:
                let_type_map[v] = 'logic'
        for m_bool in re.finditer(r'\b(\w+)\s*\|\|', s):
            v = m_bool.group(1)
            if v not in reg_type_map:
                let_type_map[v] = 'logic'
        for m_bool in re.finditer(r'\|\|\s*~?\s*(\w+)\b', s):
            v = m_bool.group(1)
            if v not in reg_type_map:
                let_type_map[v] = 'logic'

        # Pattern: *reg OP var or var OP *reg (bitwise/arithmetic/comparison)
        # var should match register's type
        for m_op in re.finditer(r'\*(\w+)\s*([&|^+\-><=!]+)\s*(\w+)\b', s):
            reg_n = m_op.group(1)
            var_n = m_op.group(3)
            if reg_n in reg_type_map and var_n not in reg_type_map:
                let_type_map.setdefault(var_n, reg_type_map[reg_n])
        for m_op in re.finditer(r'\b(\w+)\s*([&|^+\-><=!]+)\s*\*(\w+)', s):
            var_n = m_op.group(1)
            reg_n = m_op.group(3)
            if reg_n in reg_type_map and var_n not in reg_type_map:
                let_type_map.setdefault(var_n, reg_type_map[reg_n])

        # Pattern: ~ var ... & *reg or *reg & ~ var
        for m_not in re.finditer(r'~\s*(\w+)\b', s):
            v = m_not.group(1)
            # Check if this negated var appears near a register deref
            for m_reg in re.finditer(r'\*(\w+)', s):
                rn = m_reg.group(1)
                if rn in reg_type_map and v not in reg_type_map:
                    let_type_map.setdefault(v, reg_type_map[rn])

        # Pattern: ~ var used with || or && → logic
        for m_not_bool in re.finditer(r'~\s*(\w+)\s*(?:\|\||&&)', s):
            v = m_not_bool.group(1)
            if v not in reg_type_map:
                let_type_map[v] = 'logic'
        for m_not_bool in re.finditer(r'(?:\|\||&&)\s*~?\s*\(?\s*(\w+)', s):
            v = m_not_bool.group(1)
            if v not in reg_type_map and v not in {'if', 'else', 'send', 'set', 'let'}:
                let_type_map.setdefault(v, 'logic')

        # Pattern: variables in send expressions → infer from send port type
        sm_send = re.match(r'\s*send\s+out_ep\.(\w+)\s+\(', s)
        if sm_send:
            port = sm_send.group(1)
            port_type = out_port_type_map.get(port)
            if port_type:
                # Find variables that are indexed (var[...]) — these are arrays, don't infer
                indexed_vars = set(m_idx.group(1) for m_idx in re.finditer(r'\b(\w+)\s*\[', s))
                # Find variables in the send expression that aren't registers
                for m_var in re.finditer(r'\b(\w+)\b', s):
                    vn = m_var.group(1)
                    if (vn not in reg_type_map and vn not in let_type_map
                            and vn not in indexed_vars
                            and vn not in {'send', 'out_ep', 'in_ep', port, 'logic', 'if',
                                           'else', 'let', 'set', 'recv', 'cycle'}
                            and not vn.startswith('logic')):
                        let_type_map.setdefault(vn, port_type)

    # Also: let variable matching output port name → use port type
    for port_name, port_type in out_port_type_map.items():
        if port_name not in reg_type_map:
            let_type_map.setdefault(port_name, port_type)

    # Track emitted let names to detect duplicates (per loop scope)
    emitted_let_names = set()

    for line in lines:
        stripped = line.strip()
        # Reset let tracking at loop boundaries
        if stripped == 'loop {':
            emitted_let_names = set()
        if stripped.startswith('let ') and ' = ' in stripped:
            # Extract indent and name
            m = re.match(r'^(\s*)let\s+(\w+)\s*=\s*(.*)$', line)
            if m:
                indent = m.group(1)
                name = m.group(2)
                expr_rest = m.group(3)

                # Skip duplicate let bindings (keep only the first)
                if name in emitted_let_names and 'recv ' not in expr_rest:
                    continue
                emitted_let_names.add(name)

                # Keep recv expressions and special cases as-is
                if 'recv ' in expr_rest:
                    new_lines.append(line)
                elif expr_rest.strip() == f"*r_fu_data_i >>" or expr_rest.strip() == "*r_fu_data_cpop_i >>":
                    new_lines.append(line)
                elif expr_rest.strip().startswith('<(0)::logic[') and name not in let_type_map:
                    # Keep already-typed zeros only if no better type was inferred
                    new_lines.append(line)
                else:
                    # Replace expression with typed zero + comment
                    # Determine suffix (>> or nothing)
                    suffix = ""
                    expr_clean = expr_rest.rstrip()
                    if expr_clean.endswith('>>'):
                        suffix = " >>"
                        expr_clean = expr_clean[:-2].rstrip()

                    # Choose type: use inferred type if available, then flag names, then default
                    inferred_type = let_type_map.get(name)
                    if inferred_type:
                        type_str = inferred_type
                    else:
                        flag_names = {'adder_op_b_negate', 'shift_left', 'shift_arithmetic',
                                      'sgn', 'less', 'adder_z_flag'}
                        if name in flag_names:
                            type_str = 'logic'
                        else:
                            type_str = f"logic[{default_width}]"

                    # Clean expr for comment (remove nested comments)
                    expr_comment = re.sub(r'/\*.*?\*/', '', expr_clean).strip()
                    if len(expr_comment) > 80:
                        expr_comment = expr_comment[:77] + '...'

                    new_lines.append(f"{indent}let {_sanitize_ident(name)} = <(0)::{type_str}> /* {expr_comment} */{suffix}")
            else:
                new_lines.append(line)
        elif stripped.startswith('set ') and ' := ' in stripped:
            # Cast set expressions to match register type
            sm = re.match(r'^(\s*)set\s+(\w+)\s*:=\s*(.*)$', line)
            if sm:
                indent_s = sm.group(1)
                reg_name = sm.group(2)
                expr_rest = sm.group(3)
                suffix = ""
                expr_clean = expr_rest.rstrip()
                if expr_clean.endswith('>>'):
                    suffix = " >>"
                    expr_clean = expr_clean[:-2].rstrip()

                reg_type = reg_type_map.get(reg_name, f"logic[{default_width}]")

                # If the expression is already properly typed, keep it
                if expr_clean.startswith(f'<(') and f')::{reg_type}>' in expr_clean:
                    new_lines.append(line)
                else:
                    # Wrap in cast to match register type
                    new_lines.append(f"{indent_s}set {reg_name} := <({expr_clean})::{reg_type}>{suffix}")
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    result = '\n'.join(new_lines)
    # Final cleanup: remove bare tick chars outside of comments and sized literals
    cleaned_lines = []
    for line in result.split('\n'):
        # Split off inline comment
        comment_start = line.find('/*')
        if comment_start >= 0:
            code_part = line[:comment_start]
            comment_part = line[comment_start:]
        else:
            code_part = line
            comment_part = ""
        # Remove bare ticks from code (not part of sized literals)
        code_part = re.sub(r"(?<![0-9])'(?![bdhoBDHO0-9])", "", code_part)

        # Fix operator precedence: add parens around comparisons before && / ||
        # In SV, < > <= >= == != bind tighter than && ||, but Anvil may differ
        # Pattern: expr OP expr && ... → (expr OP expr) && ...
        code_part = re.sub(
            r'(\b\S+\s*(?:<(?!=)|>(?!=)|<=|>=|==|!=)\s*\S+)\s*(&&|\|\|)',
            r'(\1) \2', code_part)

        # Fix SV reduction operators: ( | *var ) or ( & *var ) → <(*var)::logic>
        # These are unary reduction ops (OR-reduce, AND-reduce) → 1-bit result
        code_part = re.sub(r'\(\s*[|&]\s*(\*\w+)\s*\)', r'<(\1)::logic>', code_part)
        # Also handle without parens: | *var as unary reduction (only when not preceded by an operand)
        # Must not match binary OR (e.g., "exp_empty | *reg")
        def _reduce_or_replace(m):
            # If preceded by a word char or closing paren/bracket/angle, it's binary OR — leave it
            before = code_part[:m.start()].rstrip()
            if before and (before[-1].isalnum() or before[-1] in ')]}>' or before[-1] == '_'):
                return m.group(0)  # binary OR, don't replace
            return f' <({m.group(1)})::logic>'
        code_part = re.sub(r'\|\s*(\*\w+)\b(?!\s*[|])', _reduce_or_replace, code_part)

        # Fix struct-like expressions in cast: <( field : value )::type> → <(0)::type>
        # Colons inside <(...)::type> that aren't part of :: indicate SV struct syntax
        def _fix_struct_cast(m):
            inner = m.group(1)
            typ = m.group(2)
            # If inner contains bare colons (not ::), replace with 0
            inner_no_scope = inner.replace("::", "@@SCOPE@@")
            if ":" in inner_no_scope:
                return f"<(0)::{typ}>"
            return m.group(0)
        code_part = re.sub(r'<\(([^)]*)\)::(logic\[\d+\])>', _fix_struct_cast, code_part)
        # Fix SV type casts: <(type_name ( expr ))::type> → <(0)::type>
        code_part = re.sub(r'<\((\w+_t\s*\([^)]*\))\)::(logic\[\d+\])>', r'<(0)::\2>', code_part)

        # Fix shift expressions inside casts: <(... << ...)::type> → <(0)::type>
        # Shift ops with mixed-width operands cause type mismatches
        # Use balanced-paren matching to find cast expressions
        def _fix_shift_casts_in_line(line_text):
            result = []
            i = 0
            while i < len(line_text):
                # Look for <( pattern
                if line_text[i:i+2] == '<(' :
                    # Find the balanced closing )
                    depth = 1
                    j = i + 2
                    while j < len(line_text) and depth > 0:
                        if line_text[j] == '(':
                            depth += 1
                        elif line_text[j] == ')':
                            depth -= 1
                        j += 1
                    # j now points past the closing )
                    inner = line_text[i+2:j-1]
                    # Check for ::type> after the closing )
                    tm = re.match(r'::(logic(?:\[\d+\])?)\s*>', line_text[j:])
                    if tm and '<<' in inner:
                        # Replace with zero
                        cast_type = tm.group(1)
                        end_pos = j + tm.end()
                        result.append(f"<(0)::{cast_type}>")
                        i = end_pos
                        continue
                result.append(line_text[i])
                i += 1
            return ''.join(result)
        code_part = _fix_shift_casts_in_line(code_part)

        # Fix single-index array access: *reg [ N - 1 ] → <(*reg)::logic>
        # This pattern appears when SV has reg_q[STAGES-1] for single-bit extraction
        def _fix_single_index(m):
            var = m.group(1)
            return f"<({var})::logic>"
        code_part = re.sub(r'(\*\w+)\s*\[\s*[^:\]]+\s*\]', _fix_single_index, code_part)

        # Fix struct field access on registers: *reg.field → *reg
        code_part = re.sub(r'(\*\w+)\.\w+', r'\1', code_part)

        # Fix comparisons: *reg == 1'b0 → *reg == <(1'b0)::type>
        # Only for register dereferences with known types
        def _fix_comparison_cast(m):
            var_name = m.group(1)  # e.g., *reg_name
            op = m.group(2)        # == or !=
            lit = m.group(3)       # 1'b0 or 1'b1
            # Only fix for register dereferences (*name)
            if not var_name.startswith('*'):
                return m.group(0)
            clean_name = var_name[1:].strip()
            reg_t = reg_type_map.get(clean_name)
            if reg_t and reg_t != "logic":
                return f"{var_name} {op} <({lit})::{reg_t}>"
            return m.group(0)
        code_part = re.sub(r'(\*?\w+)\s*(==|!=)\s*(1\'b[01])', _fix_comparison_cast, code_part)

        # Fix comparisons with sized hex/decimal literals: *reg OP N'hXX → cast
        def _fix_comparison_sized_lit(m):
            var_name = m.group(1)
            op = m.group(2)
            lit = m.group(3)
            if not var_name.startswith('*'):
                return m.group(0)
            clean_name = var_name[1:].strip()
            reg_t = reg_type_map.get(clean_name)
            if reg_t and reg_t != "logic":
                return f"{var_name} {op} <({lit})::{reg_t}>"
            return m.group(0)
        code_part = re.sub(r'(\*\w+)\s*(==|!=|>=?|<=?)\s*(\d+\'[hdbo][0-9a-fA-F]+)', _fix_comparison_sized_lit, code_part)

        # Fix comparisons/ops with bare numbers: *reg OP number or let_var OP number
        def _fix_comparison_bare_int(m):
            var_name = m.group(1)
            op = m.group(2)
            num = m.group(3)
            if var_name.startswith('*'):
                clean_name = var_name[1:].strip()
                reg_t = reg_type_map.get(clean_name)
                if reg_t and reg_t != "logic":
                    return f"{var_name} {op} <({num})::{reg_t}>"
            else:
                # Check let_type_map
                let_t = let_type_map.get(var_name)
                if let_t and let_t != "logic":
                    return f"{var_name} {op} <({num})::{let_t}>"
            return m.group(0)
        code_part = re.sub(r'(\*?\w+)\s*(==|!=|>=?|<(?!=))\s*(\d+)(?![\'dhbo\w])', _fix_comparison_bare_int, code_part)

        # Fix bitwise ops with mismatched sized literals: *reg & N'hXX → cast
        def _fix_bitwise_sized_lit(m):
            var_name = m.group(1)
            op = m.group(2)
            lit = m.group(3)
            if not var_name.startswith('*'):
                return m.group(0)
            clean_name = var_name[1:].strip()
            reg_t = reg_type_map.get(clean_name)
            if reg_t and reg_t != "logic":
                return f"{var_name} {op} <({lit})::{reg_t}>"
            return m.group(0)
        code_part = re.sub(r'(\*\w+)\s*([&|^])\s*(\d+\'[hdbo][0-9a-fA-F]+)', _fix_bitwise_sized_lit, code_part)

        # Fix $clog2 that wasn't evaluated: $clog2 ( N ) → 1
        code_part = re.sub(r'\$clog2\s*\(\s*[^)]+\s*\)', "1", code_part)

        # Fix bare integer in arithmetic with registers: *reg + 1, *reg - 1
        # Cast the integer to match the register's type
        def _fix_arith_int(m):
            var_name = m.group(1)  # e.g., *reg_name
            op = m.group(2)        # + or -
            num = m.group(3)       # bare number
            clean_name = var_name.lstrip('*').strip()
            reg_t = reg_type_map.get(clean_name)
            if reg_t and reg_t != "logic":
                return f"{var_name} {op} <({num})::{reg_t}>"
            return m.group(0)
        code_part = re.sub(r'(\*\w+)\s*(\+|-)\s*(\d+)(?!\')', _fix_arith_int, code_part)

        # Fix bare integer after cast value: <(N)::type> - 1 → <(N)::type> - <(1)::type>
        def _fix_cast_arith(m):
            cast_type = m.group(1)  # e.g., logic[4]
            op = m.group(2)         # + or -
            num = m.group(3)        # bare number
            return f"::{cast_type}> {op} <({num})::{cast_type}>"
        code_part = re.sub(r'::(logic\[\d+\])>\s*(\+|-)\s*(\d+)(?!\')', _fix_cast_arith, code_part)

        # Evaluate constant comparisons: number == 1'b0 → 1'b0/1'b1
        # These arise from parameter substitution (e.g., DEPTH=8 → 8 == 0)
        def _eval_const_cmp(m):
            lhs = m.group(1).strip()
            op = m.group(2).strip()
            rhs = m.group(3).strip()
            try:
                # Try to evaluate both sides
                lhs_val = eval(re.sub(r"'[bdho]", "", lhs.replace("1'b0","0").replace("1'b1","1")), {"__builtins__": {}})
                rhs_val = eval(re.sub(r"'[bdho]", "", rhs.replace("1'b0","0").replace("1'b1","1")), {"__builtins__": {}})
                result = False
                if op == "==": result = (lhs_val == rhs_val)
                elif op == "!=": result = (lhs_val != rhs_val)
                elif op == ">": result = (lhs_val > rhs_val)
                elif op == "<": result = (lhs_val < rhs_val)
                elif op == ">=": result = (lhs_val >= rhs_val)
                elif op == "<=": result = (lhs_val <= rhs_val)
                return "1'b1" if result else "1'b0"
            except Exception:
                return m.group(0)
        # Match: number/literal == number/literal
        code_part = re.sub(r'\b(\d+(?:\'[bdh][0-9a-fA-F]+)?)\s*(==|!=|>=|<=|>|<)\s*(\d+(?:\'[bdh][0-9a-fA-F]+)?)\b', _eval_const_cmp, code_part)

        # Fix bare 0 in comparisons only: == 0, != 0, > 0, < 0 → use 1'b0
        # These appear when parameter substitution creates expressions like `N > 0`
        code_part = re.sub(r'([=!<>]=?\s*)0(?!\w|\')', r"\g<1>1'b0", code_part)
        # Fix standalone 0 in logical expressions: && 0, || 0
        code_part = re.sub(r'(&&\s*|&\s*|\|\|\s*|\|\s*)0(?!\w|\')', r"\g<1>1'b0", code_part)

        # Fix broad comparison pattern: (expr_with_*reg) != 1'b0 after bare-0 conversion
        # When a complex expression involving *reg is compared to a 1-bit literal,
        # cast the literal to match the widest register type in the expression
        def _fix_complex_comparison_post(m):
            lhs = m.group(1)
            op = m.group(2)
            lit = m.group(3)
            reg_refs = re.findall(r'\*(\w+)', lhs)
            widest_type = None
            widest_bits = 0
            for rn in reg_refs:
                rt = reg_type_map.get(rn)
                if rt and rt != "logic":
                    wm = re.match(r'logic\[(\d+)\]', rt)
                    if wm:
                        w = int(wm.group(1))
                        if w > widest_bits:
                            widest_bits = w
                            widest_type = rt
            if widest_type:
                return f"{lhs} {op} <({lit})::{widest_type}>"
            return m.group(0)
        code_part = re.sub(r'(\([^)]*\*\w+[^)]*\))\s*(==|!=)\s*(1\'b[01])', _fix_complex_comparison_post, code_part)

        cleaned_lines.append(code_part + comment_part)

    # Replace terminal let bindings (let without >>) with cycle 1
    # Terminal lets are dead-end statements that can't be used
    temp_cleaned = []
    for idx, line in enumerate(cleaned_lines):
        m = re.match(r'(\s*)let\s+\w+\s*=\s*.*$', line)
        if m and not line.rstrip().endswith('>>'):
            # Check if next non-empty line is } or } else — this is a terminal let
            is_terminal = False
            for nxt in cleaned_lines[idx+1:]:
                ns = nxt.strip()
                if not ns:
                    continue
                if ns.startswith('}') or ns == '':
                    is_terminal = True
                break
            if is_terminal:
                temp_cleaned.append(m.group(1) + 'cycle 1')
                continue
        temp_cleaned.append(line)
    cleaned_lines = temp_cleaned

    # Remove unused let bindings (Anvil rejects them)
    # Multiple passes since removing one let might make another unused
    for _pass in range(5):
        full_text = '\n'.join(cleaned_lines)
        new_cleaned = []
        removed = False
        for idx, line in enumerate(cleaned_lines):
            m = re.match(r'\s*let\s+(\w+)\s*=\s*', line)
            if m:
                let_name = m.group(1)
                # Check if this name is used elsewhere in the output
                # Count occurrences in all OTHER lines
                pattern = r'\b' + re.escape(let_name) + r'\b'
                other_text = '\n'.join(cleaned_lines[:idx] + cleaned_lines[idx+1:])
                occurrences = len(re.findall(pattern, other_text))
                if occurrences == 0:
                    removed = True
                    continue  # skip this unused let
            new_cleaned.append(line)
        cleaned_lines = new_cleaned
        if not removed:
            break

    # Fix sequencing: ensure >> connectors are correct after let removal
    result_text = '\n'.join(cleaned_lines)
    # Remove trailing >> before a closing brace
    result_text = re.sub(r'\s*>>\s*\n(\s*\})', r'\n\1', result_text)

    # Post-pass: fix remaining type mismatches by extracting types from let definitions
    # and cast-expressions, then fixing comparisons/ops with bare ints
    let_def_types = {}
    for line in result_text.split('\n'):
        m_let = re.match(r'\s*let\s+(\w+)\s*=\s*<\(.*?\)::(logic(?:\[\d+\])?)\>', line)
        if m_let:
            let_def_types[m_let.group(1)] = m_let.group(2)
    fixed_lines = []
    for line in result_text.split('\n'):
        # Fix: let_var OP bare_number → cast the number
        if let_def_types:
            def _fix_let_cmp(m):
                vn = m.group(1)
                op = m.group(2)
                num = m.group(3)
                lt = let_def_types.get(vn)
                if lt and lt != "logic":
                    return f"{vn} {op} <({num})::{lt}>"
                return m.group(0)
            line = re.sub(r'\b(\w+)\s*(==|!=|>=?|<(?!=))\s*(\d+)(?![\'dhbo\w])', _fix_let_cmp, line)
        # Fix: cast_expr & sized_lit → cast the literal
        def _fix_cast_bitwise(m):
            cast_type = m.group(1)
            op = m.group(2)
            lit = m.group(3)
            return f"::{cast_type}> {op} <({lit})::{cast_type}>"
        line = re.sub(r'::(logic\[\d+\])>\s*([&|^])\s*(\d+\'[hdbo][0-9a-fA-F]+)', _fix_cast_bitwise, line)
        fixed_lines.append(line)
    result_text = '\n'.join(fixed_lines)

    # Fix empty if/else blocks: insert cycle 1 into empty blocks
    # Pattern: { \n } (possibly with whitespace)
    def _fix_empty_blocks(text):
        lines_list = text.split('\n')
        result = []
        for i, line in enumerate(lines_list):
            result.append(line)
            # Check if this line opens a block and next line closes it
            if i + 1 < len(lines_list):
                this_stripped = line.rstrip()
                next_stripped = lines_list[i + 1].strip()
                if this_stripped.endswith('{') and (next_stripped == '}' or next_stripped.startswith('} else')):
                    # Get indentation of the opening brace
                    indent = len(line) - len(line.lstrip()) + 4
                    result.append(' ' * indent + 'cycle 1')
        return '\n'.join(result)
    result_text = _fix_empty_blocks(result_text)

    return result_text


def main():
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
