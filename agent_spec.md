# Agent Specification: SV-to-Anvil Manual Conversion

Instructions for AI agents performing manual SystemVerilog-to-Anvil HDL conversion.

---

## Step-by-Step Conversion Process

### 1. Read and Understand the SV Module

1. Open the `.sv` file and identify the `module` declaration.
2. Note all `import` statements (e.g., `import ariane_pkg::*;`).
3. List all parameters, including `parameter type` declarations.
4. Catalog every port: name, direction (`input`/`output`/`inout`), and width.
5. Read the module body and classify each block:
   - `always_comb` → combinational logic
   - `always_ff @(posedge clk)` → sequential logic
   - `assign` → continuous combinational assignments
   - `generate` → parameterized/replicated hardware
   - Sub-module instantiations (`module_name #(...) inst_name (...);`)

### 2. Plan the Anvil Structure

1. **Name the `proc`** — use the same name as the SV module.
2. **Identify clock/reset ports** — these will be removed (Anvil handles them implicitly).
3. **Define channel classes** for port groups — every endpoint MUST reference a channel class (see "Channel Classes" section below). Group related SV ports into channel messages with appropriate lifetimes.
4. **Map ports to endpoints:**
   - `input` → `left` endpoint on a channel (proc can `recv` left messages)
   - `output` → `right` endpoint on a channel (proc can `send` left messages)
   - `inout` → requires manual review; typically split into separate channels.
5. **Plan register vs. wire:**
   - Signals written in `always_ff` → `reg` declarations in Anvil
   - Signals written in `always_comb` or `assign` → `let` bindings (inside loops)
6. **Identify sync patterns** — choose `@dyn - @#1` for typical data channels, `@dyn - @dyn` for permissive timing, or request/response patterns with `@res`.

### 3. Write the Anvil Code

Follow this order:

```
// 1. Parameter comments (manual adaptation needed)
// 2. Import comments (SV packages → manual adaptation)

// 3. Channel class definitions (REQUIRED for all endpoints)
chan input_ch {
    left data : (logic[8]@#1) @dyn - @dyn
}

chan output_ch {
    left result : (logic[8]@#1) @dyn - @dyn
}

proc module_name (
    // 4. Endpoint list — each references a channel class (no clk/rst)
    in_ep : left input_ch,
    out_ep : right output_ch
) {
    // 5. Register declarations (from always_ff signals)
    reg state : logic[4];
    reg buf : logic[8];

    // 6. Loop with recv, combinational logic, send, and sequential updates
    loop {
        let x = recv in_ep.data >>
        set buf := x + 8'd1 >>
        send out_ep.result (*buf) >>
        set state := *state + 4'd1
    }

    // 7. Sub-module instantiations (spawn with positional args)
    // spawn sub_module (endpoint_arg);
}
```

### 4. Verify the Conversion

1. Check that every SV port group has a corresponding channel class and endpoint (except clk/rst).
2. Verify every `assign` became a `let` binding inside a `loop`.
3. Verify every `always_ff` non-blocking assignment (`<=`) became `set ... :=`.
4. Verify every `always_comb` became `let` bindings or combinational expressions inside loops.
5. Confirm `case`/`unique case` became `match` with a mandatory `_ =>` default arm.
6. Check that all sub-module instantiations became `spawn` statements with positional args.
7. Compile the Anvil output with `anvil -just-check` and fix any errors.

---

## Channel Classes

**This is the most important Anvil concept.** Every proc endpoint MUST reference a channel class. You cannot use bare types like `(logic[32])` as endpoint types — the compiler rejects this.

### Defining Channel Classes

A channel class declares named messages with data types, lifetimes, and sync patterns:

```
chan my_channel {
    left msg_name : (data_type@lifetime) sync_pattern
}
```

- **`left`/`right`**: Message direction. A `left` endpoint holder can `recv` left messages and `send` right messages. A `right` endpoint holder can `send` left messages and `recv` right messages.
- **Data type**: Written as `(logic[N]@lifetime)` — the `@lifetime` is INSIDE the parentheses.
- **Sync pattern**: Controls timing between send and recv (e.g., `@dyn - @#1`).

### Lifetimes

| Lifetime | Meaning |
|----------|---------|
| `@#1` | Value lives for exactly 1 cycle — use it immediately |
| `@res` | Value lives until the response message arrives |
| `@dyn` | Dynamic lifetime — handshake-based |

### Sync Patterns

Written after the data type as `@sender_sync - @receiver_sync`:

| Pattern | Meaning |
|---------|---------|
| `@dyn - @#1` | Sender can send any time, receiver consumes within 1 cycle |
| `@#1 - @dyn` | Sender sends for 1 cycle, receiver can consume any time |
| `@dyn - @dyn` | Both sides have dynamic timing (most permissive) |
| `@#1 - @#1` | Strict: both sides synchronized to 1 cycle |

### Channel Instantiation and Spawn

Channels are instantiated with `chan left_ep -- right_ep : channel_class;` and passed to procs via `spawn`:

```
chan ep_le -- ep_ri : my_channel;
spawn some_proc(ep_le);
```

### Grouping SV Ports into Channels

- Group related inputs into one channel (e.g., all data inputs → `input_ch`)
- Group related outputs into another channel (e.g., all results → `output_ch`)
- For request/response protocols (valid/ready), use a single channel with `@res` lifetime
- Simple modules may need just one input channel and one output channel

### Example: Converting SV Ports to Channel Classes

**SystemVerilog:**
```systemverilog
module decoder(
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic [31:0] instruction_i,
    output logic        is_accel_o,
    output logic        illegal_instr_o
);
```

**Anvil:**
```
chan decoder_in_ch {
    left instr : (logic[32]@#1) @dyn - @dyn
}
chan decoder_out_ch {
    left is_accel : (logic@#1) @dyn - @dyn,
    left illegal : (logic@#1) @dyn - @dyn
}
proc decoder(
    in_ep : left decoder_in_ch,
    out_ep : right decoder_out_ch
) {
    loop {
        let instr = recv in_ep.instr >>
        send out_ep.is_accel (1'b0) >>
        send out_ep.illegal (1'b0) >>
        cycle 1
    }
}
```

---

## Construct Mapping Reference

| SystemVerilog | Anvil | Notes |
|---------------|-------|-------|
| `module name (...);` | `proc name (...) { }` | Ports become endpoints referencing channel classes |
| Port group (inputs) | `chan in_ch { left msg : (logic[N]@#1) @dyn - @dyn }` | Define a channel class for each port group |
| Port group (outputs) | `chan out_ch { left msg : (logic[N]@#1) @dyn - @dyn }` | Proc uses `right` endpoint to send `left` messages |
| `input logic [N:0] x` | `recv ep.x` (via channel endpoint) | Input data arrives through `recv` on a channel message |
| `output logic [N:0] y` | `send ep.y (value)` (via channel endpoint) | Output data sent through `send` on a channel message |
| `input logic clk_i` | *(removed)* | Implicit in Anvil |
| `input logic rst_ni` | *(removed)* | Implicit in Anvil |
| `logic [N:0] sig;` | `reg sig : logic[N+1];` | If written in `always_ff` (no parentheses on type) |
| `logic [N:0] sig;` | `let sig = ...;` | If written in `always_comb`/`assign` |
| `assign y = a + b;` | `let y = a + b;` | Combinational (must be inside a `loop`) |
| `always_comb begin ... end` | `let x = ...;` (chain) | Convert to let-bindings inside loops |
| `always_ff @(posedge clk)` | `loop { set x := ...; }` | Register write, 1-cycle delay |
| `x <= expr;` | `set x := expr;` | Non-blocking → set |
| `x = expr;` (in comb) | `let x = expr;` | Blocking → let |
| `a ? b : c` | `if a { b } else { c }` | Ternary → if-else |
| `case (sel) ... endcase` | `match sel { ... _ => () }` | Must have `_ =>` default (no trailing comma on last arm) |
| `{a, b, c}` | `#{ a, b, c }` | Concatenation |
| `module_name #(.P(V)) inst (.port(sig));` | `spawn module_name (ep)` | Positional endpoint args only (no named params) |
| `generate for (genvar i=0; ...)` | `generate (i : 0, N, 1) { }` | Parallel unroll; range is inclusive |
| `$signed(x)` | `x` | Strip — Anvil types are explicit |
| `$clog2(N)` | *(manual)* | No direct equivalent; compute or parameterize |

---

## Common Patterns and Anvil Translations

### Pattern 1: Simple Register with Reset

**SystemVerilog:**
```systemverilog
always_ff @(posedge clk_i or negedge rst_ni) begin
    if (~rst_ni)
        counter_q <= '0;
    else
        counter_q <= counter_d;
end
```

**Anvil:**
```
reg counter_q : logic[32];

loop {
    set counter_q := counter_d
}
// Reset is implicit — the Anvil compiler initializes registers
```

### Pattern 2: Combinational MUX via Case

**SystemVerilog:**
```systemverilog
always_comb begin
    unique case (sel)
        2'b00:   result = a;
        2'b01:   result = b;
        2'b10:   result = c;
        default: result = '0;
    endcase
end
```

**Anvil:**
```
// Must be inside a loop — let bindings cannot appear at proc body level
loop {
    let result = match (*sel) {
        2'b00 => *a,
        2'b01 => *b,
        2'b10 => *c,
        _ => 8'd0
    } >>
    set some_reg := result
}
```

### Pattern 3: Parameterized Bit Reversal (Generate)

**SystemVerilog:**
```systemverilog
generate
    genvar k;
    for (k = 0; k < WIDTH; k++)
        assign reversed[k] = original[WIDTH-1-k];
endgenerate
```

**Anvil:**
```
// Indexed `let` bindings are invalid — use `set` with an array register
reg reversed : logic[8][4];

loop {
    generate (k : 0, 3, 1) {
        set reversed[k] := *original[3 - k]
    } >>
    cycle 1
}
```

### Pattern 4: Sub-Module Instantiation

**SystemVerilog:**
```systemverilog
alu #(
    .CVA6Cfg(CVA6Cfg)
) i_alu (
    .clk_i     (clk_i),
    .rst_ni    (rst_ni),
    .fu_data_i (fu_data),
    .result_o  (alu_result)
);
```

**Anvil:**
```
// clk_i and rst_ni removed — implicit in Anvil
// spawn takes POSITIONAL endpoint args only (no named params)
// Parameters like CVA6Cfg require manual adaptation
chan alu_in_ch {
    left data : (logic[8]@#1) @dyn - @dyn
}
chan ep_le -- ep_ri : alu_in_ch;
spawn alu(ep_le);
```

### Pattern 5: FSM (State Machine)

**SystemVerilog:**
```systemverilog
typedef enum logic [1:0] { IDLE, LOAD, EXEC, DONE } state_t;
state_t state_q, state_d;

always_comb begin
    state_d = state_q;
    case (state_q)
        IDLE: if (start) state_d = LOAD;
        LOAD: state_d = EXEC;
        EXEC: if (done)  state_d = DONE;
        DONE: state_d = IDLE;
    endcase
end

always_ff @(posedge clk_i)
    state_q <= state_d;
```

**Anvil:**
```
enum state_t { IDLE, LOAD, EXEC, DONE }
reg state_q : state_t;

// let bindings MUST be inside loops — they cannot appear at proc body level
loop {
    let state_d = match (*state_q) {
        state_t::IDLE => state_t::LOAD,
        state_t::LOAD => state_t::EXEC,
        state_t::EXEC => state_t::DONE,
        state_t::DONE => state_t::IDLE,
        _ => *state_q
    } >>
    set state_q := state_d
}
```

### Pattern 6: Send and Receive (Port I/O)

**SystemVerilog:**
```systemverilog
module adder(
    input  logic [7:0] a_i,
    input  logic [7:0] b_i,
    output logic [7:0] sum_o
);
    assign sum_o = a_i + b_i;
endmodule
```

**Anvil:**
```
chan adder_io_ch {
    left req : (logic[8]@res),
    right res : (logic[8]@#1)
}

proc adder(ep : left adder_io_ch) {
    reg result : logic[8];
    loop {
        let a = recv ep.req >>
        set result := a + 8'd1 >>
        send ep.res (*result) >>
        cycle 1
    }
}
```

---

## Error-Prone Areas

1. **Forgetting to remove clk/rst ports.** Anvil handles these implicitly. Leaving them produces invalid Anvil.
2. **Using bare types as endpoint types.** Endpoints MUST reference channel classes — `port : right (logic[32])` is a syntax error. Define a `chan` first.
3. **Using `=` instead of `:=` in set statements.** Anvil uses `set x := expr;` (not `set x = expr;`).
4. **Missing `_ =>` default in match.** Anvil requires an exhaustive default arm in every `match`. Do NOT use a trailing comma on the last arm.
5. **Reading registers without `*` dereference.** In Anvil, `reg` values are read with `*reg_name`, not bare `reg_name`.
6. **Confusing `>>` (sequential) with `;` (parallel).** In Anvil, `a; b` runs both in parallel; `a >> b` runs sequentially. This is the opposite of most programming languages.
7. **Width mismatches.** SV `[31:0]` is 32 bits → Anvil `logic[32]`. Off-by-one errors are common when computing `MSB - LSB + 1`.
8. **Parenthesized reg types.** Use `reg x : logic[8];` NOT `reg x : (logic[8]);` — parentheses create a Tuple type instead of an Array, causing type mismatch warnings.
9. **`let` bindings outside loops.** `let` is an expression form that must appear inside `loop { }`, not at proc body level. The compiler rejects `let` at the top level.
10. **Named spawn parameters.** `spawn` takes positional endpoint arguments ONLY. `spawn foo(name = ep)` is a syntax error — use `spawn foo(ep)`.
11. **Indexed `let` bindings.** `let x[k] = expr` is a syntax error. Use `set` with array registers instead.
12. **`$signed`/`$unsigned` casts.** Strip these; Anvil's type system handles signedness differently.
13. **Multi-driver signals.** SV allows a signal to be assigned in multiple `always` blocks. Anvil does not — consolidate into a single expression.
14. **Timing of `set`.** `set` takes effect **next cycle**, not immediately. If SV code reads a value after a non-blocking assignment in the same cycle, the Anvil equivalent must use a separate `let` for the combinational value.
15. **Borrow checking.** Values received from channels have limited lifetimes. A value with `@#1` lifetime must be used within 1 cycle. A value with `@res` lifetime lives until the response. Do not mutate borrowed registers between `send` and `recv`.

---

## Quality Checklist

Before submitting a converted file:

- [ ] Channel classes defined for all port groups with appropriate lifetimes and sync patterns
- [ ] All clk/rst ports removed from endpoint list
- [ ] Every endpoint references a channel class (no bare types)
- [ ] All `assign` statements converted to `let` bindings inside loops
- [ ] All `always_comb` blocks converted to `let` bindings or `match` expressions inside loops
- [ ] All `always_ff` blocks converted to `reg` declarations + `loop { set ... }` blocks
- [ ] All `case`/`unique case` converted to `match` with `_ =>` default (no trailing comma on last arm)
- [ ] All sub-module instantiations converted to `spawn` with positional args (without clk/rst)
- [ ] All SV literals use width-prefixed Anvil format (`32'd0`, not `'0`)
- [ ] No bare register reads — all use `*` dereference
- [ ] Concatenation uses `#{ }` syntax, not `{ }`
- [ ] Register types use bare `logic[N]` (no parentheses)
- [ ] All `let` bindings are inside `loop { }` blocks
- [ ] Input data received via `recv` on channel endpoints
- [ ] Output data sent via `send` on channel endpoints
- [ ] Parameters documented as comments (manual adaptation needed)
- [ ] Generate blocks use `set` with array registers (not indexed `let`)
- [ ] No `$signed`/`$unsigned`/`$clog2` function calls remaining
- [ ] File compiles with `anvil -just-check` without errors
