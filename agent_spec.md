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
3. **Map ports to endpoints:**
   - `input` → `right` endpoint (data flows in)
   - `output` → `left` endpoint (data flows out)
   - `inout` → requires manual review; typically split into separate `left`/`right` endpoints.
4. **Plan register vs. wire:**
   - Signals written in `always_ff` → `reg` declarations in Anvil
   - Signals written in `always_comb` or `assign` → `let` bindings
5. **Identify channel classes** if ports form a protocol (e.g., valid/ready handshake → single channel with `@dyn` lifetime).

### 3. Write the Anvil Code

Follow this order:

```
// 1. Parameter comments (manual adaptation needed)
// 2. Import comments (SV packages → manual adaptation)

proc module_name (
    // 3. Endpoint list (no clk/rst)
    port_a : right (logic[WIDTH]),
    port_b : left (logic[WIDTH])
) {
    // 4. Register declarations (from always_ff signals)
    reg state : (logic[4]);

    // 5. Combinational logic (let bindings from assign/always_comb)
    let sum = a + b;

    // 6. Sequential logic (loop + set from always_ff)
    loop {
        set state := next_state;
    }

    // 7. Sub-module instantiations (spawn)
    spawn sub_module (endpoint_args);
}
```

### 4. Verify the Conversion

1. Check that every SV port has a corresponding Anvil endpoint (except clk/rst).
2. Verify every `assign` became a `let` binding.
3. Verify every `always_ff` non-blocking assignment (`<=`) became `set ... :=`.
4. Verify every `always_comb` became `let` bindings or combinational expressions.
5. Confirm `case`/`unique case` became `match` with a mandatory `_ =>` default arm.
6. Check that all sub-module instantiations became `spawn` statements.
7. Compile the Anvil output and compare the generated SV against the original.

---

## Construct Mapping Reference

| SystemVerilog | Anvil | Notes |
|---------------|-------|-------|
| `module name (...);` | `proc name (...) { }` | Ports become endpoints |
| `input logic [N:0] x` | `x : right (logic[N+1])` | Width = MSB - LSB + 1 |
| `output logic [N:0] y` | `y : left (logic[N+1])` | Width = MSB - LSB + 1 |
| `input logic clk_i` | *(removed)* | Implicit in Anvil |
| `input logic rst_ni` | *(removed)* | Implicit in Anvil |
| `logic [N:0] sig;` | `reg sig : (logic[N+1]);` | If written in `always_ff` |
| `logic [N:0] sig;` | `let sig = ...;` | If written in `always_comb`/`assign` |
| `assign y = a + b;` | `let y = a + b;` | Combinational |
| `always_comb begin ... end` | `let x = ...;` (chain) | Convert to let-bindings |
| `always_ff @(posedge clk)` | `loop { set x := ...; }` | Register write, 1-cycle delay |
| `x <= expr;` | `set x := expr;` | Non-blocking → set |
| `x = expr;` (in comb) | `let x = expr;` | Blocking → let |
| `a ? b : c` | `if a { b } else { c }` | Ternary → if-else |
| `case (sel) ... endcase` | `match sel { ... _ => (), }` | Must have `_ =>` default |
| `{a, b, c}` | `#{ a, b, c }` | Concatenation |
| `module_name #(.P(V)) inst (.port(sig));` | `spawn module_name (sig)` | Instantiation |
| `generate for (genvar i=0; ...)` | `generate (i : 0, N, 1) { }` | Parallel unroll |
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
reg counter_q : (logic[32]);

loop {
    set counter_q := counter_d;
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
let result = match sel {
    2'b00 => a,
    2'b01 => b,
    2'b10 => c,
    _ => 1'b0,
};
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
generate (k : 0, WIDTH, 1) {
    let reversed[k] = original[WIDTH - 1 - k];
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
// clk_i and rst_ni connections removed — implicit in Anvil
spawn alu /* CVA6Cfg */ (
    fu_data_i = fu_data,
    result_o = alu_result,
);
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

// Combinational next-state logic
let state_d = match *state_q {
    state_t::IDLE => if start { state_t::LOAD } else { *state_q },
    state_t::LOAD => state_t::EXEC,
    state_t::EXEC => if done { state_t::DONE } else { *state_q },
    state_t::DONE => state_t::IDLE,
    _ => *state_q,
};

// Sequential update
loop {
    set state_q := state_d;
}
```

---

## Error-Prone Areas

1. **Forgetting to remove clk/rst ports.** Anvil handles these implicitly. Leaving them produces invalid Anvil.
2. **Using `=` instead of `:=` in set statements.** Anvil uses `set x := expr;` (not `set x = expr;`).
3. **Missing `_ =>` default in match.** Anvil requires an exhaustive default arm in every `match`.
4. **Reading registers without `*` dereference.** In Anvil, `reg` values are read with `*reg_name`, not bare `reg_name`.
5. **Confusing `>>` (sequential) with `;` (parallel).** In Anvil, `a; b` runs both in parallel; `a >> b` runs sequentially. This is the opposite of most programming languages.
6. **Width mismatches.** SV `[31:0]` is 32 bits → Anvil `(logic[32])`. Off-by-one errors are common when computing `MSB - LSB + 1`.
7. **Parametric widths.** SV `[CVA6Cfg.XLEN-1:0]` → Anvil `(logic[CVA6Cfg.XLEN])`. Simplify `MSB-1:0` to just `MSB`.
8. **`$signed`/`$unsigned` casts.** Strip these; Anvil's type system handles signedness differently.
9. **Multi-driver signals.** SV allows a signal to be assigned in multiple `always` blocks. Anvil does not — consolidate into a single expression.
10. **Timing of `set`.** `set` takes effect **next cycle**, not immediately. If SV code reads a value after a non-blocking assignment in the same cycle, the Anvil equivalent must use a separate `let` for the combinational value.

---

## Quality Checklist

Before submitting a converted file:

- [ ] All clk/rst ports removed from endpoint list
- [ ] Every SV port has a corresponding Anvil endpoint with correct direction and width
- [ ] All `assign` statements converted to `let` bindings
- [ ] All `always_comb` blocks converted to `let` bindings or `match` expressions
- [ ] All `always_ff` blocks converted to `reg` declarations + `loop { set ... }` blocks
- [ ] All `case`/`unique case` converted to `match` with `_ =>` default
- [ ] All sub-module instantiations converted to `spawn` (without clk/rst connections)
- [ ] All SV literals use width-prefixed Anvil format (`32'd0`, not `'0`)
- [ ] No bare register reads — all use `*` dereference
- [ ] Concatenation uses `#{ }` syntax, not `{ }`
- [ ] Parameters documented as comments (manual adaptation needed)
- [ ] Generate blocks converted to `generate` or `generate_seq` where possible
- [ ] No `$signed`/`$unsigned`/`$clog2` function calls remaining
- [ ] File compiles with Anvil compiler without errors
- [ ] Generated SV from Anvil is functionally equivalent to original
