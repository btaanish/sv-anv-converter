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
- **Channel classes** (`chan`) — REQUIRED for all endpoints; bare types like `(logic[32])` are invalid as endpoint types
- Registers (`reg`, `set`, `*` dereference) — writes are 1-cycle delayed; types use bare `logic[N]` (no parentheses)
- Expressions: `let` bindings (must be inside `loop`), `match`, `if/else`, `#{ }` concatenation
- **`send`/`recv`** — how data flows through channel endpoints (replaces SV port reads/writes)
- Timing: `>>` (sequential wait), `;` (parallel join), `cycle N`
- Threads: `loop { }` for continuous hardware behavior
- Instantiation: `spawn` for sub-processes — positional endpoint args only (no named params)
- Lifetimes: `@#1` (one cycle), `@res` (until response), `@dyn` (dynamic handshake)
- Sync patterns: `@dyn - @#1`, `@dyn - @dyn`, `@#1 - @#1`, etc.
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

1. **Define channel classes** — this is the MOST IMPORTANT step:
   - Group related SV inputs into an input channel class
   - Group related SV outputs into an output channel class
   - For request/response protocols (valid/ready), use a single channel with `@res` lifetime
   - Choose sync patterns: `@dyn - @dyn` for permissive timing, `@dyn - @#1` for typical data
   - Every endpoint MUST reference a channel class — bare types are a syntax error
2. Write the `proc` signature: name, endpoint list (skip clk/rst). Each endpoint references a channel class with `left` or `right` direction.
3. Decide which signals are `reg` (written in `always_ff`) vs `let` (combinational). Remember: `let` bindings must be inside `loop { }`.
4. Plan `send`/`recv` operations for data I/O through channel endpoints.
5. Identify any constructs that need manual handling (see "Unsupported Constructs" below).

### Phase 3: Write Anvil

Follow this template:

```
// Converted from: <original_filename.sv>
// Parameters — adapt manually:
// param WIDTH = 32

// Channel class definitions (REQUIRED — define BEFORE the proc)
chan input_ch {
    left data : (logic[8]@#1) @dyn - @dyn
}

chan output_ch {
    left result : (logic[8]@#1) @dyn - @dyn
}

proc <module_name> (
    in_ep : left input_ch,
    out_ep : right output_ch
) {
    // Register declarations (bare logic[N], no parentheses)
    reg <name> : logic[8];

    // All logic inside loops — recv inputs, compute, send outputs
    loop {
        let <input> = recv in_ep.data >>
        set <name> := <input> + 8'd1 >>
        send out_ep.result (*<name>) >>
        cycle 1
    }

    // Sub-module instantiations (positional args only)
    // spawn <module> (<endpoint>);
}
```

### Phase 4: Verify

1. Review against the quality checklist in `agent_spec.md`.
2. Compile with `anvil -just-check <file>`.
3. Compare Anvil-generated SV output against the original SV for functional equivalence.
4. Fix any discrepancies and re-verify.

---

## Key Mapping Rules

These are the same rules that `sv2anvil.py` implements, for manual application:

### Ports → Channel Classes + Endpoints

**Every SV port group must become a channel class.** You cannot use bare types as endpoint types.

| SV Port Group | Anvil Channel + Endpoint | Example |
|--------------|--------------------------|---------|
| Input signals | `chan in_ch { left msg : (logic[N]@#1) @dyn - @dyn }` + `left` endpoint | Proc `recv`s data via `recv ep.msg` |
| Output signals | `chan out_ch { left msg : (logic[N]@#1) @dyn - @dyn }` + `right` endpoint | Proc `send`s data via `send ep.msg (val)` |
| Req/resp protocol | `chan io_ch { left req : (T@res), right res : (T@#1) }` + `left` endpoint | Proc `recv`s req, `send`s res |
| `inout` | Split into separate input and output channels | Bidirectional requires two endpoints |

### Direction Mapping (within channel context)

| SV Direction | Channel Endpoint | Why | Data Flow |
|-------------|-----------------|-----|-----------|
| `input` | `left` endpoint on channel | Proc with `left` ep can `recv` left messages | `let x = recv ep.msg` |
| `output` | `right` endpoint on channel | Proc with `right` ep can `send` left messages | `send ep.msg (val)` |
| `inout` | Split into `left` + `right` on separate channels | Bidirectional requires two endpoints | Both `send` and `recv` |

### Lifetime and Sync Pattern Guide

| Use Case | Lifetime | Sync Pattern | Notes |
|----------|----------|-------------|-------|
| Simple data passing | `@#1` | `@dyn - @dyn` | Most permissive, good default |
| Streaming data | `@#1` | `@dyn - @#1` | Receiver must consume within 1 cycle |
| Request/response | `@res` (req), `@#1` (resp) | *(implicit)* | Request value lives until response arrives |
| Handshake protocol | `@dyn` | `@dyn - @dyn` | Dynamic timing on both sides |

### Width Conversion

| SV Width | Anvil Type |
|----------|-----------|
| `logic` (no range) | `logic` |
| `logic [N-1:0]` | `logic[N]` |
| `logic [7:0]` | `logic[8]` |
| `logic [MSB:LSB]` | `logic[MSB - LSB + 1]` |

**Important:** Use bare `logic[N]` for register types (no parentheses). Parenthesized `(logic[N])` creates a Tuple type, causing type mismatch warnings.

### Clk/Rst Removal

Remove ports matching these names: `clk`, `clk_i`, `clk_o`, `clock`, `rst`, `rst_i`, `rst_ni`, `rst_n`, `reset`, `areset`.

Also remove any connections to these signals in sub-module instantiations.

### Assignment Conversion

| SV | Anvil | Context |
|----|-------|---------|
| `assign x = expr;` | `let x = expr;` | Combinational (must be inside `loop`) |
| `x = expr;` (in `always_comb`) | `let x = expr;` | Blocking combinational (inside `loop`) |
| `x <= expr;` (in `always_ff`) | `set x := expr;` | Non-blocking sequential |
| Reading input port | `let x = recv ep.msg` | Input data via channel `recv` |
| Driving output port | `send ep.msg (value)` | Output data via channel `send` |

### Control Flow

| SV | Anvil |
|----|-------|
| `if (cond) ... else ...` | `if cond { ... } else { ... }` |
| `a ? b : c` | `if a { b } else { c }` |
| `case (sel) ... endcase` | `match sel { ... _ => () }` (no trailing comma on last arm) |
| `for (genvar i=0; i<N; i++)` | `generate (i : 0, N-1, 1) { }` (range is inclusive) |

### Miscellaneous

| SV | Anvil |
|----|-------|
| `{a, b, c}` | `#{ a, b, c }` |
| `$signed(x)` | `x` (strip) |
| `module #(.P(V)) inst (.port(sig));` | `spawn module (ep);` (positional args only) |
| `typedef enum logic [1:0] { A, B }` | `enum name { A, B }` |
| `typedef struct packed { ... }` | `struct name { ... }` |

---

## Timing Handling

Timing is the most nuanced part of SV-to-Anvil conversion. Refer to **`timing_handling.md`** for the full guide. Key points:

- **Clock/reset are implicit** in Anvil — never declare them as endpoints.
- **`set` is always 1-cycle delayed** — equivalent to SV non-blocking `<=` on posedge clk.
- **`let` is combinational** — equivalent to SV `assign` or blocking `=` in `always_comb`. Must be inside `loop { }`.
- **`loop { }` models continuous hardware** — wraps sequential logic that runs every cycle.
- **`>>` sequences operations across cycles** — use for multi-cycle behavior.
- **Register reads use `*`** — `*counter` reads the current value; `set counter := *counter + 1` increments.
- **Borrow checking** — values received from channels have limited lifetimes:
  - `@#1` values must be used within 1 cycle (before any `set` or `cycle`)
  - `@res` values live until the response message is sent
  - Do not mutate borrowed registers between `send` and `recv`
- **Every loop path must take ≥ 1 cycle** — add `cycle 1` or use `set` (which takes 1 cycle).

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
- Defined M channel classes with lifetimes/sync patterns
- Converted K always_ff blocks to reg+set
- Converted J always_comb blocks to let bindings inside loops
- N spawn instantiations (positional args)
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
