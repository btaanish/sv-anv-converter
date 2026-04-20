#!/usr/bin/env python3
"""Post-processing script to fix type errors in generated Anvil code.

Fixes three categories of errors:
1. Operator precedence: SV's == binds tighter than &, but Anvil's & binds
   tighter than ==.  Add parens around comparisons in & chains.
2. Index out of bounds: bit-select on logic[N] where index >= N should use
   shift+cast instead of array indexing.
3. Double casts: <<(expr)::T>::T> collapsed to <(expr)::T>.

Usage:
    python3 fix_anvil_types.py input.anvil > fixed.anvil
    python3 fix_anvil_types.py input.anvil --in-place
"""

import re
import sys


# ---------------------------------------------------------------------------
# 1. Fix operator precedence  (& / | vs == / !=)
# ---------------------------------------------------------------------------
# In SV:  == / != bind tighter than & / | / ^
# In Anvil:  & / | bind tighter than == / !=
#
# The converter copies SV precedence assumptions, so we need to add explicit
# parentheses around comparisons when they appear in & / | chains.
#
# Strategy: tokenize and find comparisons (==, !=) that have & or | neighbors
# at the same nesting level, then wrap the comparison and its operands.

def _find_matching_open_paren(text, close_pos):
    """Find the matching '(' for a ')' at close_pos."""
    depth = 0
    i = close_pos
    while i >= 0:
        if text[i] == ')':
            depth += 1
        elif text[i] == '(':
            depth -= 1
            if depth == 0:
                return i
        i -= 1
    return -1


def fix_precedence(line):
    """Add parentheses around comparisons in & / | chains."""
    # Find all == and != operators and check context
    # We process from right to left to preserve positions
    comparisons = []
    i = 0
    while i < len(line):
        if line[i] in '({[':
            # skip balanced groups to avoid modifying nested contexts
            pass
        if i < len(line) - 1 and line[i:i+2] in ('==', '!='):
            # Make sure it's not inside ::
            if i > 0 and line[i-1] == ':':
                i += 2
                continue
            comparisons.append(i)
            i += 2
            continue
        i += 1

    if not comparisons:
        return line

    result = line
    offset = 0
    for cmp_pos in comparisons:
        adj_pos = cmp_pos + offset
        cmp_op = result[adj_pos:adj_pos+2]

        # Find the left operand boundary
        # Walk left from cmp_pos, skip whitespace, then collect the operand
        left_end = adj_pos
        # skip whitespace before ==
        li = adj_pos - 1
        while li >= 0 and result[li] == ' ':
            li -= 1
        if li < 0:
            continue

        # Left operand could be: ) closing a paren group, or an identifier/deref
        if result[li] == ')':
            left_start = _find_matching_open_paren(result, li)
            if left_start < 0:
                continue
        else:
            # Walk back to find start of identifier (including * prefix)
            left_start = li
            while left_start > 0 and (result[left_start-1].isalnum() or result[left_start-1] in '_*'):
                left_start -= 1

        # Find the right operand boundary
        ri = adj_pos + 2
        while ri < len(result) and result[ri] == ' ':
            ri += 1
        # Right operand: literal or identifier, possibly with cast <(...)::TYPE>
        right_start = ri
        if ri < len(result) and result[ri] == '<':
            # Cast expression - find matching >
            # Must handle >> (shift) inside casts without confusing depth
            depth = 0
            while ri < len(result):
                if result[ri] == '<':
                    depth += 1
                elif result[ri] == '>':
                    # Check if this is >> (shift operator, not cast close)
                    if ri + 1 < len(result) and result[ri+1] == '>' and depth == 1:
                        # Only treat as shift if we're inside parens (part of expr)
                        # Check if there's a matching ( before
                        ri += 2  # skip >>
                        continue
                    depth -= 1
                    if depth == 0:
                        ri += 1
                        break
                ri += 1
        else:
            # Skip * dereference prefix
            if ri < len(result) and result[ri] == '*':
                ri += 1
            # Literal or identifier
            while ri < len(result) and (result[ri].isalnum() or result[ri] in "'_hHdDbBoOxXzZ"):
                ri += 1
        right_end = ri

        # Check if there's a & or | before the left operand OR after the right operand
        before_left = result[:left_start].rstrip()
        after_right = result[right_end:].lstrip()
        has_bitop_before = before_left.endswith('&') or before_left.endswith('|') or before_left.endswith('^')
        has_bitop_after = after_right.startswith('&') or after_right.startswith('|') or after_right.startswith('^')
        if not (has_bitop_before or has_bitop_after):
            continue

        # Wrap the comparison in parens
        result = result[:left_start] + '(' + result[left_start:right_end] + ')' + result[right_end:]
        offset += 2

    return result


# ---------------------------------------------------------------------------
# 2. Fix index out of bounds
# ---------------------------------------------------------------------------
# Build a map of variable -> declared width from:
#   reg VAR : logic[N];
#   let VAR = <(...)::logic[N]>
# Then fix VAR [ K ] where K >= N  ->  <(VAR >> K)::logic>

_REG_DECL = re.compile(r'reg\s+(\w+)\s*:\s*logic\[(\d+)\]')
_LET_DECL = re.compile(r'let\s+(\w+)\s*=\s*<\([^)]*\)::logic\[(\d+)\]\>')


def _build_type_map(lines):
    """Parse declarations to build var -> width mapping."""
    types = {}
    for line in lines:
        for m in _REG_DECL.finditer(line):
            types[m.group(1)] = int(m.group(2))
        for m in _LET_DECL.finditer(line):
            types[m.group(1)] = int(m.group(2))
    return types


# Pattern: EXPR [ NUMBER ]  where EXPR is a variable reference (possibly with *)
_INDEX_PAT = re.compile(r'(\*?\w+)\s*\[\s*(\d+)\s*\]')


def fix_index_oob(line, type_map):
    """Replace out-of-bounds array indexing with shift+cast."""
    def replace_index(m):
        var_ref = m.group(1)
        index = int(m.group(2))
        # Strip leading * for lookup
        var_name = var_ref.lstrip('*')
        if var_name in type_map:
            width = type_map[var_name]
            if index >= width:
                # Out of bounds: this is a bit-select, use shift+cast
                return f'<({var_ref} >> {index})::logic>'
        return m.group(0)
    return _INDEX_PAT.sub(replace_index, line)


# ---------------------------------------------------------------------------
# 3. Fix double casts
# ---------------------------------------------------------------------------
# <<(expr)::TYPE>::TYPE>  ->  <(expr)::TYPE>
_DOUBLE_CAST = re.compile(r'<\s*<\(([^)]*)\)::(logic(?:\[\d+\])?)\s*>\s*::\s*(logic(?:\[\d+\])?)\s*>')


def fix_double_cast(line):
    """Collapse double casts where outer and inner types match."""
    def replace_double(m):
        expr = m.group(1)
        inner_type = m.group(2)
        outer_type = m.group(3)
        if inner_type == outer_type:
            return f'<({expr})::{outer_type}>'
        # Keep outer cast if types differ
        return m.group(0)
    return _DOUBLE_CAST.sub(replace_double, line)


# ---------------------------------------------------------------------------
# 4. Fix wrong let declaration types
# ---------------------------------------------------------------------------
# The converter often initializes let bindings with <(0)::logic[N]> where N
# is wrong.  We detect the correct type from how the variable is used in
# send statements: send ... (<(VAR)::TYPE>).  If the send cast type differs
# from the declaration type, fix the declaration.

_LET_PLACEHOLDER = re.compile(
    r'(let\s+(\w+)\s*=\s*<\(0\))::logic(?:\[(\d+)\])?(>.*)'
)
_SEND_CAST = re.compile(
    r'<\(\s*(\w+)\s*\)::(logic(?:\[\d+\])?)\s*>'
)
# Match casts like <(EXPR)::TYPE> where EXPR mentions a variable
_EXPR_CAST = re.compile(
    r'<\([^)]*\)::(logic(?:\[\d+\])?)\s*>'
)


def fix_let_types(lines):
    """Fix let declaration types based on cast usage context."""
    # First pass: collect cast types for each variable from send and set statements
    cast_types = {}  # var -> set of types
    # Also collect variables that appear in set := <(...)::TYPE> context
    _set_cast = re.compile(r'set\s+(\w+)\s*:=\s*<\([^)]*\)::(logic(?:\[\d+\])?)\s*>')

    for line in lines:
        # From send statements: send ... (<(VAR)::TYPE>)
        if 'send ' in line:
            for m in _SEND_CAST.finditer(line):
                var = m.group(1)
                cast_type = m.group(2)
                if var not in cast_types:
                    cast_types[var] = set()
                cast_types[var].add(cast_type)

    # Also look for variables used in set statements where the var is the
    # sole content of the cast: set REG := <(VAR)::TYPE>
    _set_var_cast = re.compile(r'set\s+\w+\s*:=\s*<\(\s*(\w+)\s*\)::(logic(?:\[\d+\])?)\s*>')
    for line in lines:
        if 'set ' in line:
            for m in _set_var_cast.finditer(line):
                var = m.group(1)
                cast_type = m.group(2)
                if var not in cast_types:
                    cast_types[var] = set()
                cast_types[var].add(cast_type)

    # Collect all let placeholder declarations
    let_decls = {}  # var -> (line_idx, declared_type)
    for idx, line in enumerate(lines):
        m = _LET_PLACEHOLDER.match(line.lstrip())
        if m:
            var = m.group(2)
            decl_width = m.group(3)
            decl_type = f'logic[{decl_width}]' if decl_width else 'logic'
            let_decls[var] = (idx, decl_type)

    # Infer types from comparison with sized literals:
    # VAR == N'hX or VAR != N'hX => VAR should be logic[N]
    _cmp_literal = re.compile(r'(\w+)\s*(?:==|!=)\s*(\d+)\'[hHdDbBoO]')
    for line in lines:
        for m in _cmp_literal.finditer(line):
            var = m.group(1)
            width = int(m.group(2))
            if var in let_decls:
                _, decl_type = let_decls[var]
                inferred = f'logic[{width}]' if width > 1 else 'logic'
                if decl_type != inferred:
                    if var not in cast_types:
                        cast_types[var] = set()
                    cast_types[var].add(inferred)

    # For variables NOT in cast_types, try to infer from boolean usage
    # Patterns that indicate a variable should be logic (1-bit):
    # - ~ VAR (direct NOT)
    # - if VAR (condition)
    # - ~ ( VAR & ... ) (VAR in boolean AND inside NOT)
    _bool_patterns = [
        re.compile(r'~\s*(\w+)'),           # ~ VAR
        re.compile(r'if\s+(\w+)\s'),         # if VAR
        re.compile(r'~\s*\(\s*(\w+)\s*&'),   # ~ ( VAR &
        re.compile(r'~\s*\(\s*[^)]*&\s*(\w+)\s*\)'),  # ~ ( ... & VAR )
    ]
    for line in lines:
        for pat in _bool_patterns:
            for m in pat.finditer(line):
                var = m.group(1)
                if var in let_decls and var not in cast_types:
                    _, decl_type = let_decls[var]
                    if decl_type != 'logic':
                        cast_types[var] = {'logic'}

    # Fix declarations
    result = []
    for idx, line in enumerate(lines):
        m = _LET_PLACEHOLDER.match(line.lstrip())
        if m:
            indent = line[:len(line) - len(line.lstrip())]
            var = m.group(2)
            decl_width = m.group(3)
            decl_type = f'logic[{decl_width}]' if decl_width else 'logic'

            if var in cast_types and len(cast_types[var]) == 1:
                correct_type = next(iter(cast_types[var]))
                if correct_type != decl_type:
                    prefix = m.group(1)
                    suffix = m.group(4)
                    line = f'{indent}{prefix}::{correct_type}{suffix}'
        result.append(line)
    return result


# ---------------------------------------------------------------------------
# 5. Fix SV reduction operators
# ---------------------------------------------------------------------------
# SV reduction operators like |expr, &expr produce 1-bit results.
# The converter leaves them as ( | VAR ) or ( & VAR ).
# Fix: ( | VAR ) -> (VAR != N'h0), ( & VAR ) -> (VAR == N'hFF..F)

_REDUCTION_OR = re.compile(r'\(\s*\|\s*(\*?\w+)\s*\)')
_REDUCTION_AND = re.compile(r'\(\s*&\s*(\*?\w+)\s*\)')


def fix_reduction_ops(line, type_map):
    """Fix SV reduction operators."""
    def replace_red_or(m):
        var_ref = m.group(1)
        var_name = var_ref.lstrip('*')
        if var_name in type_map:
            width = type_map[var_name]
            zero = f"{width}'h" + '0' * ((width + 3) // 4)
            return f'({var_ref} != {zero})'
        # Unknown width - can't fix reliably
        return m.group(0)

    def replace_red_and(m):
        var_ref = m.group(1)
        var_name = var_ref.lstrip('*')
        if var_name in type_map:
            width = type_map[var_name]
            allones = f"{width}'h" + 'F' * ((width + 3) // 4)
            return f'({var_ref} == {allones})'
        return m.group(0)

    line = _REDUCTION_OR.sub(replace_red_or, line)
    line = _REDUCTION_AND.sub(replace_red_and, line)
    return line


# ---------------------------------------------------------------------------
# 6. Fix commented-out bit-range slices
# ---------------------------------------------------------------------------
# The converter comments out bit-range selections: VAR /* [H:L] */
# These should become: <(VAR >> L)::logic[H-L+1]>

_BIT_RANGE_COMMENT = re.compile(
    r'(\*?\w+)\s*/\*\s*\[(\d+):(\d+)\]\s*\*/'
)


def fix_bit_range_comments(line):
    """Convert commented-out bit-range slices to shift+cast expressions."""
    def replace_range(m):
        var_ref = m.group(1)
        high = int(m.group(2))
        low = int(m.group(3))
        width = high - low + 1
        if low == 0:
            return f'<({var_ref})::logic[{width}]>'
        else:
            return f'<({var_ref} >> {low})::logic[{width}]>'
    return _BIT_RANGE_COMMENT.sub(replace_range, line)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process(text):
    lines = text.split('\n')

    # Fix let declaration types first (affects type_map)
    lines = fix_let_types(lines)

    type_map = _build_type_map(lines)

    result = []
    for line in lines:
        line = fix_bit_range_comments(line)
        line = fix_precedence(line)
        line = fix_reduction_ops(line, type_map)
        line = fix_index_oob(line, type_map)
        line = fix_double_cast(line)
        result.append(line)
    return '\n'.join(result)


def main():
    if len(sys.argv) < 2:
        print("Usage: fix_anvil_types.py <file.anvil> [--in-place]", file=sys.stderr)
        sys.exit(1)

    filepath = sys.argv[1]
    in_place = '--in-place' in sys.argv

    with open(filepath, 'r') as f:
        text = f.read()

    fixed = process(text)

    if in_place:
        with open(filepath, 'w') as f:
            f.write(fixed)
    else:
        print(fixed, end='')


if __name__ == '__main__':
    main()
