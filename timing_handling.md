# Timing Handling: SV-to-Anvil Conversion

How to convert timing-related constructs from SystemVerilog to Anvil HDL.

---

## 1. How SystemVerilog Handles Timing

### Explicit Clock and Reset

Every sequential module in SV declares clock and reset as ports:

```systemverilog
module counter (
    input  logic        clk_i,    // Clock signal
    input  logic        rst_ni,   // Active-low reset
    input  logic        enable_i,
    output logic [31:0] count_o
);
```

### `always_ff @(posedge clk)` — Sequential Logic

All flip-flop behavior is explicitly clocked:

```systemverilog
always_ff @(posedge clk_i or negedge rst_ni) begin
    if (~rst_ni)
        count_q <= 32'd0;         // Reset value
    else if (enable_i)
        count_q <= count_q + 1;   // Clocked update
end
```

Key characteristics:
- **Non-blocking assignment (`<=`)** — takes effect at the next clock edge
- **Sensitivity list** explicitly names the clock edge and optional async reset
- **Reset logic** is manually coded inside the `always_ff` block
- **Same-cycle reads** of the register see the old value (before the `<=` takes effect)

### `always_comb` — Combinational Logic

Combinational blocks have no clock dependency:

```systemverilog
always_comb begin
    count_d = count_q + 1;   // Blocking = immediate, no clock
end
```

### Multiple Clock Domains

SV supports multiple clocks by declaring separate clock ports and using different sensitivity lists:

```systemverilog
always_ff @(posedge clk_a) begin
    reg_a <= data_a;
end

always_ff @(posedge clk_b) begin
    reg_b <= data_b;
end
```

---

## 2. How Anvil Handles Timing

### Implicit Clock

Anvil does **not** declare clock or reset as ports. The clock is implicit:

- Every `reg` is automatically clocked
- Every `set` takes effect on the next implicit clock edge
- The `cycle N` construct delays execution by N clock cycles

### Registers: `reg` + `set`

```
reg count : (logic[32]);         // Declare a 32-bit register

loop {
    set count := *count + 1;     // Write: takes effect next cycle
}                                // *count reads current value
```

Key characteristics:
- **`set x := expr`** — always delayed by exactly one cycle (equivalent to SV `<=`)
- **`*x`** — dereference to read current register value
- **No manual reset** — the compiler/toolchain handles register initialization
- **No sensitivity list** — the clock is implicit

### Combinational Logic: `let`

```
let sum = a + b;                 // Combinational — immediate, no clock
```

`let` bindings compute within the current cycle, equivalent to SV `assign` or blocking `=`.

### Lifetimes — Compile-Time Timing Contracts

Anvil's type system encodes when values are valid:

| Lifetime | Meaning | SV Equivalent |
|----------|---------|---------------|
| `@#1` | Valid for exactly 1 cycle | Single-cycle register output |
| `@#N` | Valid for N cycles | Pipeline register chain |
| `@#msg + N` | Valid for N cycles after a message | Latency-aware pipeline |
| `@dyn` | Valid until acknowledged | Handshake (valid/ready) protocol |

Lifetimes are checked at compile time and generate **no additional hardware** — they prevent reading stale data or timing hazards.

### Sequencing Operators

| Operator | Meaning | Timing |
|----------|---------|--------|
| `e1 >> e2` | Sequential: evaluate e1, wait, then e2 | Spans multiple cycles |
| `e1; e2` | Parallel: start both, wait for both | Same cycle start |
| `cycle N` | Explicit delay of N cycles | N-cycle wait |

---

## 3. The Conversion Strategy

### Step 1: Eliminate clk/rst Ports

Remove all clock and reset ports from the module interface. They become implicit.

**SV:**
```systemverilog
module foo (
    input  logic clk_i,
    input  logic rst_ni,
    input  logic [7:0] data_i,
    output logic [7:0] data_o
);
```

**Anvil:**
```
proc foo (
    data_i : right (logic[8]),
    data_o : left (logic[8])
) {
```

Known clk/rst signal names: `clk`, `clk_i`, `clk_o`, `clock`, `rst`, `rst_i`, `rst_ni`, `rst_n`, `reset`, `areset`.

### Step 2: Convert `always_ff` to `reg` + `set`

For each `always_ff` block:

1. **Declare `reg`** for every signal that receives a non-blocking assignment (`<=`).
2. **Strip the reset branch** — Anvil handles reset implicitly.
3. **Convert `<=` to `set :=`** inside a `loop { }` block.
4. **Replace bare register reads with `*` dereference.**

**SV:**
```systemverilog
logic [31:0] counter_q;

always_ff @(posedge clk_i or negedge rst_ni) begin
    if (~rst_ni)
        counter_q <= 32'd0;
    else if (enable)
        counter_q <= counter_q + 32'd1;
end
```

**Anvil:**
```
reg counter_q : (logic[32]);

loop {
    if enable {
        set counter_q := *counter_q + 32'd1;
    }
}
```

### Step 3: Convert `always_comb` to `let` Bindings

Each combinational assignment becomes a `let`:

**SV:**
```systemverilog
always_comb begin
    next_state = current_state;
    case (current_state)
        IDLE: if (start) next_state = RUNNING;
        RUNNING: if (done) next_state = IDLE;
    endcase
end
```

**Anvil:**
```
let next_state = match *current_state {
    state_t::IDLE => if start { state_t::RUNNING } else { *current_state },
    state_t::RUNNING => if done { state_t::IDLE } else { *current_state },
    _ => *current_state,
};
```

### Step 4: Convert Sub-Module Instantiations

Remove clk/rst connections when converting instantiations to `spawn`:

**SV:**
```systemverilog
alu #(.WIDTH(32)) i_alu (
    .clk_i   (clk_i),
    .rst_ni  (rst_ni),
    .op_a    (operand_a),
    .op_b    (operand_b),
    .result  (alu_result)
);
```

**Anvil:**
```
spawn alu /* WIDTH=32 */ (
    op_a = operand_a,
    op_b = operand_b,
    result = alu_result,
);
```

---

## 4. Lifetime Inference from SV Timing Patterns

When converting, determine the appropriate Anvil lifetime for each signal/channel based on how it is used in SV.

### Single-Cycle Validity → `@#1`

If a signal is valid for exactly one clock cycle (typical for pipeline registers):

```systemverilog
// SV: data valid for one cycle after posedge
always_ff @(posedge clk_i) data_q <= data_d;
```

```
// Anvil: reg with @#1 lifetime on channel
reg data_q : (logic[WIDTH]) /* @#1 */;
```

### Pipeline Latency → `@#msg + N`

If data passes through N pipeline stages:

```systemverilog
// SV: 3-stage pipeline
always_ff @(posedge clk_i) stage1_q <= input_data;
always_ff @(posedge clk_i) stage2_q <= stage1_q;
always_ff @(posedge clk_i) stage3_q <= stage2_q;
```

```
// Anvil: sequential pipeline with cycle delays
reg stage1 : (logic[WIDTH]);
reg stage2 : (logic[WIDTH]);
reg stage3 : (logic[WIDTH]);

loop {
    set stage1 := input_data >>
    set stage2 := *stage1 >>
    set stage3 := *stage2;
}
```

### Handshake Protocol → `@dyn`

If SV uses valid/ready handshaking:

```systemverilog
// SV: AXI-style handshake
output logic       valid_o,
output logic [7:0] data_o,
input  logic       ready_i
```

```
// Anvil: single channel with @dyn lifetime
// The valid/ready signals are generated automatically
data_out : left channel_class @dyn
```

### Combinational (No Latency) → Direct `let`

Signals that are purely combinational (no register, no clock) have no lifetime concern:

```systemverilog
assign sum = a + b;  // Available same cycle
```

```
let sum = a + b;  // Immediate, no lifetime annotation needed
```

---

## 5. Examples of Common Timing Patterns

### Example 1: Loadable Counter

**SV:**
```systemverilog
module loadable_counter (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic        load_i,
    input  logic        enable_i,
    input  logic [15:0] load_val_i,
    output logic [15:0] count_o
);
    logic [15:0] count_q;
    assign count_o = count_q;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (~rst_ni)
            count_q <= 16'd0;
        else if (load_i)
            count_q <= load_val_i;
        else if (enable_i)
            count_q <= count_q + 16'd1;
    end
endmodule
```

**Anvil:**
```
proc loadable_counter (
    load_i     : right logic,
    enable_i   : right logic,
    load_val_i : right (logic[16]),
    count_o    : left (logic[16])
) {
    reg count_q : (logic[16]);

    let count_o = *count_q;

    loop {
        if load_i {
            set count_q := load_val_i;
        } else {
            if enable_i {
                set count_q := *count_q + 16'd1;
            }
        }
    }
}
```

### Example 2: Pipeline Register

**SV:**
```systemverilog
module pipe_stage (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic        valid_i,
    input  logic [31:0] data_i,
    output logic        valid_o,
    output logic [31:0] data_o
);
    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (~rst_ni) begin
            valid_o <= 1'b0;
            data_o  <= 32'd0;
        end else begin
            valid_o <= valid_i;
            data_o  <= data_i;
        end
    end
endmodule
```

**Anvil:**
```
proc pipe_stage (
    valid_i : right logic,
    data_i  : right (logic[32]),
    valid_o : left logic,
    data_o  : left (logic[32])
) {
    reg valid_q : logic;
    reg data_q  : (logic[32]);

    let valid_o = *valid_q;
    let data_o  = *data_q;

    loop {
        set valid_q := valid_i;
        set data_q  := data_i;
    }
}
```

### Example 3: Shift Register

**SV:**
```systemverilog
module shift_reg #(parameter WIDTH = 8, DEPTH = 4) (
    input  logic             clk_i,
    input  logic             rst_ni,
    input  logic [WIDTH-1:0] data_i,
    output logic [WIDTH-1:0] data_o
);
    logic [WIDTH-1:0] stage [DEPTH-1:0];

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (~rst_ni) begin
            for (int i = 0; i < DEPTH; i++) stage[i] <= '0;
        end else begin
            stage[0] <= data_i;
            for (int i = 1; i < DEPTH; i++) stage[i] <= stage[i-1];
        end
    end

    assign data_o = stage[DEPTH-1];
endmodule
```

**Anvil:**
```
// param WIDTH = 8
// param DEPTH = 4

proc shift_reg (
    data_i : right (logic[WIDTH]),
    data_o : left (logic[WIDTH])
) {
    // Registers for each pipeline stage
    generate (i : 0, DEPTH, 1) {
        reg stage_i : (logic[WIDTH]);
    }

    let data_o = *stage_3;  // stage[DEPTH-1]

    loop {
        set stage_0 := data_i;
        generate_seq (i : 1, DEPTH, 1) {
            set stage_i := *stage_(i-1);
        }
    }
}
```

---

## 6. Edge Cases

### Multiple Clock Domains

**Problem:** Anvil documentation does not describe multi-clock domain support. The implicit clock model assumes a single clock domain.

**Strategy:**
- If the SV module uses only one clock, convert normally (remove the clock port).
- If the SV module crosses clock domains (e.g., CDC synchronizers, async FIFOs):
  1. **Flag with `// [UNSUPPORTED] Multi-clock domain`**
  2. Leave the module as a comment block or blackbox.
  3. Escalate to the team — this may require Anvil language extensions or a wrapper approach.

**Example CDC pattern to watch for:**
```systemverilog
// Two different clocks in sensitivity lists = multi-clock domain
always_ff @(posedge clk_a) sync_stage1 <= async_input;
always_ff @(posedge clk_b) sync_stage2 <= some_other_signal;
```

### Asynchronous Resets

**Problem:** SV explicitly codes async reset (`negedge rst_ni` in sensitivity list). Anvil's reset is implicit.

**Strategy:**
- **Strip the reset branch entirely.** Anvil's compiler handles register initialization.
- The reset value from SV (e.g., `<= 32'd0`) is lost. If a specific non-zero reset value is critical, document it as `// [VERIFY] Reset value was X in SV`.
- For modules where the reset value matters for correctness (e.g., FSM initial state), verify that Anvil's default initialization matches the SV reset value.

**SV with async reset:**
```systemverilog
always_ff @(posedge clk_i or negedge rst_ni) begin
    if (~rst_ni)
        state_q <= IDLE;     // Reset to IDLE
    else
        state_q <= state_d;
end
```

**Anvil:**
```
reg state_q : state_t;
// [VERIFY] SV reset value was IDLE — confirm Anvil default init matches

loop {
    set state_q := state_d;
}
```

### Clock Gating

**Problem:** SV uses clock gating cells to reduce power:

```systemverilog
// Gated clock: clk_gated = clk & enable
always_ff @(posedge clk_gated) begin
    data_q <= data_d;
end
```

**Strategy:**
- Convert the gated register to a **conditional set**:

```
reg data_q : (logic[WIDTH]);

loop {
    if enable {
        set data_q := data_d;
    }
    // When enable is low, register holds its value (no set issued)
}
```

This preserves the power-saving intent: the register only updates when enabled.

### Negative-Edge Clocking

**Problem:** Some SV modules use `negedge clk`:

```systemverilog
always_ff @(negedge clk_i) begin
    data_q <= data_d;
end
```

**Strategy:**
- Anvil's implicit clock does not support edge selection.
- Flag with `// [UNSUPPORTED] Negative-edge clocking`.
- If the design can be restructured to use positive edge, do so.
- Otherwise, leave as a blackbox for manual handling.

### Synchronous Reset

**Problem:** Some SV uses synchronous reset (reset inside `always_ff` but not in sensitivity list):

```systemverilog
always_ff @(posedge clk_i) begin
    if (rst)
        data_q <= '0;
    else
        data_q <= data_d;
end
```

**Strategy:**
- Treat identically to async reset: strip the reset branch, let Anvil handle initialization.
- The synchronous reset signal (`rst`) should still be removed from the port list if it's a standard reset signal.

### Latch Inference

**Problem:** `always_latch` or incomplete `always_comb` in SV infers latches:

```systemverilog
always_latch begin
    if (enable) data_q = data_d;
end
```

**Strategy:**
- Anvil has no latch primitive.
- Flag with `// [UNSUPPORTED] Latch — redesign as register or combinational logic`.
- If possible, convert to a register with conditional set (similar to clock gating approach).
