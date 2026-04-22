# Anvil Correctness Audit Report

**Auditor:** Finn
**Date:** 2026-04-22
**Issue:** tbc-db #3
**Files Audited:** `agent_spec.md`, `worker_skill.md`, `sv2anvil.py`
**Reference Material:** `anvil_ground_truth/` (9 compiler-validated examples + report.md), Anvil official docs (languageReference.html, communication.html)

---

## Executive Summary

All three files contain significant Anvil correctness issues. The most critical:

1. **agent_spec.md** teaches bare-type endpoints (`port_a : right (logic[32])`) which is **invalid Anvil syntax** — the compiler rejects it. Endpoints MUST reference channel classes.
2. **sv2anvil.py** destroys all combinational logic during post-processing by replacing every `let` binding expression with `<(0)::type>` — making every converted module semantically dead (outputs are always zero).
3. **worker_skill.md** inherits the same bare-type endpoint misconception from agent_spec.md.

---

## 1. agent_spec.md — Detailed Findings

### Confirmed by Official Docs

The Anvil Language Reference (docs.anvil.kisp-lab.org/languageReference.html) confirms:
- Proc endpoints MUST reference channel classes: `proc-endpoint ::= identifier ":" ( "left" | "right" ) identifier`
- `let` is an EXPRESSION form (`let x = e1 >> e2`), not a statement — it cannot appear at proc body level
- `spawn` takes positional endpoint args only: `"spawn" identifier "(" identifier ("," identifier)* ")"`
- `reg` syntax: `reg $identifier : $data-type-expression;` — bare `logic[8]` is the correct type, `(logic[8])` wraps in a tuple
- Sync pattern `@dyn - @dyn` is valid but "equivalent to writing no synchronization pattern" — weakest contract
- Valid sync patterns: `@dyn - @#1`, `@#1 - @dyn`, `@#1 - @#1`, `@#msg + n - @#msg + n`, `@dyn - @#msg`, `@#msg - @dyn`, `@dyn - @dyn`

### CRITICAL: Bare-Type Endpoints (Lines 43-47)

**The code example shows:**
```
proc module_name (
    port_a : right (logic[WIDTH]),
    port_b : left (logic[WIDTH])
) { ... }
```

**Compiler result:** `Syntax error` at `(logic[WIDTH])`. **Endpoints MUST reference channel class names**, not bare types.

**Correct pattern (from ground truth 09_parameterized.anvil):**
```
chan data_ch {
    left data : (logic[8]@#1) @dyn - @#1
}
proc Producer(ep : right data_ch) { ... }
```

**Fix needed:** Lines 43-61 must be rewritten to show channel definitions before proc, and endpoints referencing chan classes.

### CRITICAL: Mapping Table (Lines 81-82) — Wrong Endpoint Syntax

| Line | Shows | Should Be |
|------|-------|-----------|
| 81 | `x : right (logic[N+1])` | `x_ep : right some_chan_class` |
| 82 | `y : left (logic[N+1])` | `y_ep : left some_chan_class` |

The entire mapping table needs a row explaining that port groups become channel classes with message definitions.

### ERROR: `let` Outside Loop (Lines 218-228, Pattern 5 FSM)

**The spec shows:**
```
let state_d = match *state_q {
    state_t::IDLE => if start { state_t::LOAD } else { *state_q },
    ...
};
loop {
    set state_q := state_d;
}
```

**Compiler result:** `Syntax error` at `let` — `let` bindings cannot appear at proc body level outside a `loop`. They must be inside `loop { }`.

**Fix:** Move the `let state_d` inside the loop:
```
loop {
    let state_d = match (*state_q) {
        state_t::IDLE => if start { state_t::LOAD } else { *state_q },
        ...
    } >>
    set state_q := state_d
}
```

But note: `start` and `done` would need to come from recv on channel endpoints.

### ERROR: `reg` with Parenthesized Type (Lines 49, 118)

**The spec shows:** `reg state : (logic[4]);`

**Compiler behavior:** This compiles but creates a TUPLE type `Tuple(Array[4](Logic))` instead of `Array[4](Logic)`. Arithmetic on tuples generates warnings: `Invalid argument types: Tuple (Array[8] (Logic)) and Array[8] (Logic)`.

**Ground truth always uses:** `reg counter : logic[8];` (NO parentheses)

**Fix:** Remove parentheses from all `reg` type annotations in examples.

### ERROR: Indexed `let` in Generate (Lines 162-166, Pattern 3)

**The spec shows:**
```
generate (k : 0, WIDTH, 1) {
    let reversed[k] = original[WIDTH - 1 - k];
}
```

**Compiler result:** `Syntax error` at `[k]` — indexed `let` bindings are invalid.

**Fix:** Use `set` with array registers:
```
generate (k : 0, WIDTH, 1) {
    set reversed[k] := *original[WIDTH - 1 - k]
}
```
(Requires `reversed` to be a `reg` array.)

### ERROR: Named Spawn Parameters (Lines 185-189, Pattern 4)

**The spec shows:**
```
spawn alu /* CVA6Cfg */ (
    fu_data_i = fu_data,
    result_o = alu_result,
);
```

**Compiler result:** `Syntax error` at `=` — `spawn` takes positional endpoint arguments only.

**Correct (from ground truth):**
```
spawn alu(some_endpoint);
```

### WARNING: Match Default `_ => ()` (Line 93)

`_ => ()` compiles, but the mapping table doesn't mention that `()` is the unit value. This is confusing and could lead workers to think `()` means "do nothing". In practice, `()` takes zero cycles, which may violate the "every path must take >= 1 cycle" rule if the match is inside a loop without other cycle-consuming operations.

### MISSING: Channel Class Documentation

The spec has NO section explaining how to define channel classes (`chan`), message types, lifetimes (`@#1`, `@res`, `@dyn`), or sync patterns. This is the MOST IMPORTANT Anvil concept and it's completely absent from the conversion guide.

### MISSING: `send`/`recv` in Mapping Table

The mapping table has no entries for how SV ports become channel messages accessed via `send`/`recv`. Workers are told ports become endpoints but not how data flows through them.

---

## 2. worker_skill.md — Detailed Findings

### CRITICAL: Same Bare-Type Endpoint Error (Lines 61, 75-77)

The template shows `<endpoint_list>` without any guidance that endpoints must reference channel classes. The mapping rules (Lines 109-113) show:

| SV Direction | Anvil Endpoint |
|---|---|
| `input` | `right` |
| `output` | `left` |

This is misleading — it implies a 1:1 port-to-endpoint mapping with bare types.

### MISSING: Channel Class Creation Workflow

Phase 2 (Plan Anvil Structure) says "Identify channel classes if ports form a protocol" (line 33) but provides NO guidance on:
- How to group ports into channels
- How to choose lifetimes and sync patterns
- That EVERY endpoint MUST reference a channel class

### MISSING: `send`/`recv` in Assignment Conversion (Lines 132-136)

The assignment conversion table maps SV assigns to Anvil `let`/`set` but never mentions `send`/`recv`. In Anvil, module outputs go through `send` on channel endpoints, not through `let` bindings. This fundamental pattern is undocumented.

### WARNING: Direction Mapping May Be Confusing

The mapping `input → right` and `output → left` is correct in isolation, but without explaining channel semantics, workers may not understand that:
- A `left` endpoint holder can recv `left` messages and send `right` messages
- A `right` endpoint holder can send `left` messages and recv `right` messages

---

## 3. sv2anvil.py — Detailed Findings

### CRITICAL: Post-Processing Destroys All Combinational Logic (Lines 2587-2639)

The post-processing step replaces EVERY `let` binding expression with `<(0)::type>`:

```python
new_lines.append(f"{indent}let {_sanitize_ident(name)} = <(0)::{type_str}> /* {expr_comment} */{suffix}")
```

This means:
- `let state_d = *state_q` becomes `let state_d = <(0)::logic[32]> /* *state_q */`
- `let result = *a & *b` becomes `let result = <(0)::logic[32]> /* *a & *b */`
- ALL combinational logic is replaced with zero constants

**Impact:** Every converted module produces only zero outputs. The FSM test case showed `state_d` hardcoded to 0, meaning the state machine never transitions. The original expression is preserved as a comment but is functionally dead code.

**This is the most severe issue in the converter.** It makes every converted file semantically incorrect.

### CRITICAL: `set` Expressions Wrapped in Casts (Lines 2642-2664)

Every `set` expression is wrapped in a cast:
```python
new_lines.append(f"{indent_s}set {reg_name} := <({expr_clean})::{reg_type}>{suffix}")
```

Example: `set state_q := state_d` becomes `set state_q := <(state_d)::logic[32]>`.

While this compiles, it masks type errors and can produce incorrect behavior when `state_d` is the wrong width.

### HIGH: Hardcoded `@dyn - @dyn` Sync Pattern (Line 2156)

```python
lines.append(f"    left {msg.name} : ({msg.anvil_type}@#1) @dyn - @dyn{comma}")
```

All channel messages get `@dyn - @dyn`. While this compiles, it's semantically different from the typical `@dyn - @#1` pattern used in ground truth. `@dyn - @dyn` means both sides can have dynamic timing, which imposes different constraints on the borrow checker. The ground truth predominantly uses `@dyn - @#1`.

### HIGH: All Channel Messages Are `left` (Line 2156)

Every message in both input and output channels is declared as `left`:
```python
lines.append(f"    left {msg.name} : ...")
```

This works because:
- Input channel: all messages `left` → proc with `left` endpoint can recv them ✓
- Output channel: all messages `left` → proc with `right` endpoint can send them ✓

However, this is semantically odd. A more natural mapping would use `left` for messages flowing into the proc and `right` for messages flowing out. This impacts readability but doesn't cause compilation errors.

### HIGH: CVA6Cfg Parameters Hardcoded to 31 (Line 1259)

```python
expr_msb = re.sub(r'CVA6Cfg\.\w+', '31', expr_msb)
```

All `CVA6Cfg.XXX` references (XLEN, PLEN, etc.) are replaced with `31`, making every signal 32 bits regardless of actual parameter values. This is incorrect for many CVA6 signals.

### MEDIUM: State Machine Registers Default to `logic[32]` (Line 1770)

```python
regs.append(AnvilReg(name=rn, anvil_type="logic[32]"))
```

NBA targets without signal declarations default to 32-bit registers. In the FSM test, `state_q` (a 2-bit enum) becomes `logic[32]`.

### MEDIUM: Array Indexing Replaced with Cast (Lines 2750-2755)

```python
code_part = re.sub(r'(\*\w+)\s*\[\s*[^:\]]+\s*\]', _fix_single_index, code_part)
```

`*reg[N-1]` is replaced with `<(*reg)::logic>` — converting array access to a 1-bit cast, losing the indexing semantics entirely.

### MEDIUM: Struct Field Access Stripped (Lines 2757-2758)

```python
code_part = re.sub(r'(\*\w+)\.\w+', r'\1', code_part)
```

`*reg.field` becomes `*reg` — struct field access is silently removed, reading the entire struct instead of the specific field.

### LOW: `$clog2` Replaced with 1 (Line 2823)

```python
code_part = re.sub(r'\$clog2\s*\(\s*[^)]+\s*\)', "1", code_part)
```

All `$clog2(N)` calls become `1`, which is incorrect for any N > 2.

---

## 4. Summary of Required Fixes

### agent_spec.md — 8 fixes needed

| Priority | Location | Issue | Fix |
|----------|----------|-------|-----|
| CRITICAL | Lines 43-47 | Bare-type endpoints | Rewrite to show channel class definitions + endpoint references |
| CRITICAL | Lines 81-82 | Mapping table bare types | Add channel class column |
| CRITICAL | Lines 218-228 | `let` outside loop | Move inside loop |
| ERROR | Lines 49, 118 | Parenthesized reg type | Remove parentheses: `reg x : logic[N];` |
| ERROR | Lines 162-166 | Indexed `let` in generate | Use `set` with array reg |
| ERROR | Lines 185-189 | Named spawn params | Use positional: `spawn alu(ep)` |
| MISSING | N/A | No channel class docs | Add full section on channels, lifetimes, sync |
| MISSING | N/A | No send/recv mapping | Add to mapping table |

### worker_skill.md — 4 fixes needed

| Priority | Location | Issue | Fix |
|----------|----------|-------|-----|
| CRITICAL | Lines 61, 75-77 | No channel class guidance | Add channel creation to template and workflow |
| CRITICAL | Lines 109-113 | Direction mapping lacks channel context | Expand to show full channel class + endpoint pattern |
| MISSING | N/A | No send/recv in assignment conversion | Add send/recv row to assignment table |
| MISSING | N/A | No lifetime/sync pattern guidance | Add section on choosing @#1, @dyn, @res |

### sv2anvil.py — 8 fixes needed

| Priority | Location | Issue | Fix |
|----------|----------|-------|-----|
| CRITICAL | Lines 2587-2639 | All `let` exprs replaced with zero | Remove or rework post-processing to preserve original expressions |
| CRITICAL | Line 2156 | Hardcoded `@dyn - @dyn` | Use `@dyn - @#1` as default |
| HIGH | Line 1259 | CVA6Cfg hardcoded to 31 | Use configurable param defaults or leave symbolic |
| HIGH | Lines 2750-2755 | Array index → cast | Preserve array indexing syntax |
| HIGH | Lines 2757-2758 | Struct field stripped | Preserve struct field access |
| MEDIUM | Line 1770 | Default reg width 32 | Infer from usage context |
| MEDIUM | Lines 2642-2664 | All `set` wrapped in cast | Only cast when type mismatch detected |
| LOW | Line 2823 | `$clog2` → 1 | Compute actual value when possible |

---

## 5. Compiler Test Results

| Test | Source | Compiles? | Semantically Correct? |
|------|--------|-----------|----------------------|
| Bare-type endpoint | agent_spec.md L43 | **NO** — syntax error | N/A |
| `let` outside loop | agent_spec.md L218 | **NO** — syntax error | N/A |
| Named spawn params | agent_spec.md L185 | **NO** — syntax error | N/A |
| Indexed `let` in generate | agent_spec.md L162 | **NO** — syntax error | N/A |
| Parens in reg type | agent_spec.md L49 | Yes (with warnings) | **NO** — creates Tuple not Array |
| Match as expression | agent_spec.md L142 | Yes | Yes |
| `_ => ()` in match | agent_spec.md L93 | Yes | Yes (but confusing) |
| Counter pattern | agent_spec.md L118 | Yes (with warnings) | **NO** — Tuple type mismatch |
| Converter: simple decoder | sv2anvil.py | Yes | **YES** (trivial — outputs are constants) |
| Converter: FSM | sv2anvil.py | Yes | **NO** — all comb logic is zero |
| `@dyn - @dyn` sync | sv2anvil.py | Yes | Debatable — compiles but semantics differ from ground truth |
