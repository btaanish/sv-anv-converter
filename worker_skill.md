# Worker Skill: SV-to-Anvil Manual Converter

Skill file for workers performing manual SystemVerilog-to-Anvil HDL conversion.

---

## Role Definition

You are an HDL conversion worker. Your job is to take a SystemVerilog (`.sv`) source file and produce a functionally equivalent Anvil (`.anvil`) output file. You follow a structured workflow, apply known mapping rules, and produce clean, compilable Anvil code.

## Responsibilities

- Convert assigned SV modules to Anvil, one file at a time
- Preserve functional behavior exactly — the Anvil-compiled SV must match the original
- Flag constructs you cannot convert and leave them as clearly marked comments
- Follow commit conventions and output format specified below
- Report issues or blockers to your manager via tbc-db

---

## Required Knowledge

### SystemVerilog

You must understand:
- Module declarations, port lists, parameters (`parameter`, `localparam`, `parameter type`)
- Data types: `logic`, `wire`, `reg`, packed/unpacked arrays, structs, enums, typedefs
- Procedural blocks: `always_comb`, `always_ff @(posedge clk)`, `always_latch`
- Assignments: `assign` (continuous), `=` (blocking), `<=` (non-blocking)
- Control: `if/else`, `case`/`unique case`, `for`, `generate`
- Sub-module instantiation with named port connections
- Packages and imports (`import pkg::*;`)

### Anvil HDL

You must understand:
- Processes (`proc`), endpoints (`left`/`right`), channel classes
- Registers (`reg`, `set`, `*` dereference) — writes are 1-cycle delayed
- Expressions: `let` bindings, `match`, `if/else`, `#{ }` concatenation
- Timing: `>>` (sequential wait), `;` (parallel join), `cycle N`
- Threads: `loop { }` for continuous hardware behavior
- Instantiation: `spawn` for sub-processes
- Lifetimes: `@#1` (one cycle), `@dyn` (dynamic handshake)
- Implicit clock and reset — no explicit clk/rst ports

---

## Conversion Workflow

### Phase 1: Read SV

1. Open the SV file. Read the entire module.
2. List all ports with direction, type, and width.
3. Identify clk/rst ports (to be removed).
4. Catalog all internal signals and classify as register or wire.
5. Note all `always_ff`, `always_comb`, `assign`, `generate`, and instantiation blocks.
6. Note all parameter dependencies and package imports.

### Phase 2: Plan Anvil Structure

1. Write the `proc` signature: name, endpoint list (skip clk/rst).
2. Decide which signals are `reg` (written in `always_ff`) vs `let` (combinational).
3. Plan the ordering of declarations and logic blocks.
4. Identify any constructs that need manual handling (see "Unsupported Constructs" below).

### Phase 3: Write Anvil

Follow this template:

```
// Converted from: <original_filename.sv>
// Parameters — adapt manually:
// param WIDTH = 32

// Channel class definitions for each port group
chan input_ch {
    left data : (logic[32]@#1) @#1 - @#1
}
chan output_ch {
    left data : (logic[32]@#1) @#1 - @#1
}

proc <module_name> (
    // Endpoints reference channel classes, not bare types
    in_port : left input_ch,
    out_port : right output_ch
) {
    // Register declarations (no parens around type)
    reg <name> : logic[32];

    // Sequential logic with combinational let bindings inside loop
    loop {
        let <name> = <expr> >>
        set <name> := <expr>
    }

    // Sub-module instantiations (positional args only)
    // spawn <module>(<endpoints>);
}
```

### Phase 4: Verify

1. Review against the quality checklist in `agent_spec.md`.
2. Compile with the Anvil compiler.
3. Compare Anvil-generated SV output against the original SV for functional equivalence.
4. Fix any discrepancies and re-verify.

---

## Key Mapping Rules

These are the same rules that `sv2anvil.py` implements, for manual application:

### Ports

| SV Direction | Anvil Endpoint | Rationale |
|-------------|----------------|-----------|
| `input` | `left <chan_class>` | Data flows in; must define a `chan` class first |
| `output` | `right <chan_class>` | Data flows out; must define a `chan` class first |
| `inout` | Split into `left` + `right` | Bidirectional requires two endpoints with channel classes |

### Width Conversion

| SV Width | Anvil Type (for `reg`) | Notes |
|----------|-----------|-------|
| `logic` (no range) | `logic` | Single bit |
| `logic [N-1:0]` | `logic[N]` | No parens — `(logic[N])` creates a Tuple |
| `logic [7:0]` | `logic[8]` | No parens around type |
| `logic [MSB:LSB]` | `logic[MSB - LSB + 1]` | No parens around type |

### Clk/Rst Removal

Remove ports matching these names: `clk`, `clk_i`, `clk_o`, `clock`, `rst`, `rst_i`, `rst_ni`, `rst_n`, `reset`, `areset`.

Also remove any connections to these signals in sub-module instantiations.

### Assignment Conversion

| SV | Anvil | Context |
|----|-------|---------|
| `assign x = expr;` | `let x = expr >>` | Combinational; `let` must be inside `loop` |
| `x = expr;` (in `always_comb`) | `let x = expr >>` | Blocking combinational; inside `loop` |
| `x <= expr;` (in `always_ff`) | `set x := expr;` | Non-blocking sequential |

### Control Flow

| SV | Anvil |
|----|-------|
| `if (cond) ... else ...` | `if cond { ... } else { ... }` |
| `a ? b : c` | `if a { b } else { c }` |
| `case (sel) ... endcase` | `match sel { ... _ => () }` (no trailing comma) |
| `for (genvar i=0; i<N; i++)` | `generate (i : 0, N, 1) { }` |

### Miscellaneous

| SV | Anvil |
|----|-------|
| `{a, b, c}` | `#{ a, b, c }` |
| `$signed(x)` | `x` (strip) |
| `module #(.P(V)) inst (.port(sig));` | `spawn module (sig);` |
| `typedef enum logic [1:0] { A, B }` | `enum name { A, B }` |
| `typedef struct packed { ... }` | `struct name { ... }` |

---

## Timing Handling

Timing is the most nuanced part of SV-to-Anvil conversion. Refer to **`timing_handling.md`** for the full guide. Key points:

- **Clock/reset are implicit** in Anvil — never declare them as endpoints.
- **`set` is always 1-cycle delayed** — equivalent to SV non-blocking `<=` on posedge clk.
- **`let` is combinational** — equivalent to SV `assign` or blocking `=` in `always_comb`.
- **`loop { }` models continuous hardware** — wraps sequential logic that runs every cycle.
- **`>>` sequences operations across cycles** — use for multi-cycle behavior.
- **Register reads use `*`** — `*counter` reads the current value; `set counter := *counter + 1` increments.

---

## Unsupported Constructs

Leave these as comments with `// [UNSUPPORTED]` prefix:

- `always_latch` — no direct Anvil equivalent
- `initial` blocks — not synthesizable in Anvil
- Tri-state / `inout` with `z` — requires manual channel design
- `$clog2` and other system functions — compute manually or parameterize
- Multi-clock domain logic — see `timing_handling.md` edge cases
- Memory arrays (`reg [7:0] mem [0:255]`) — unclear Anvil RAM inference support

---

## Output Format and Commit Conventions

### File Naming

- Input: `<module_name>.sv`
- Output: `<module_name>.anvil`
- Place output files in the corresponding conversion output directory.

### Commit Messages

Use this format:
```
[AgentName] Convert <module_name>.sv to Anvil

- Converted N ports (removed clk/rst)
- Converted M always_ff blocks to reg+set
- Converted K always_comb blocks to let bindings
- N spawn instantiations
- Flagged: <any unsupported constructs>
```

### Branch Naming

Work on your assigned branch: `agentname/description`

### Comment Markers in Output

Use these markers for items needing review:

- `// [TODO] ...` — needs manual work
- `// [UNSUPPORTED] ...` — construct has no Anvil equivalent
- `// [VERIFY] ...` — converted but confidence is low
- `// [PARAM] ...` — parameter that needs manual adaptation
