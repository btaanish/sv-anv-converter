# SystemVerilog to Anvil Mapping Guide

This guide documents how every common SystemVerilog construct maps to correct Anvil HDL.
All Anvil examples are compiler-verified with `/opt/opam/default/bin/anvil -just-check`
unless explicitly marked as **pseudocode**.

Sources:
- `anvil_ground_truth/examples/` — 9 compiler-verified Anvil files
- `anvil_ground_truth/report.md` — validated syntax rules and failure analysis
- `core/cva6/core/` — CVA6 SystemVerilog source patterns

---

## 1. Module Structure

### SV Module → Anvil `proc`

SystemVerilog modules become Anvil processes (`proc`). Clock and reset ports are implicit
in Anvil — they do not appear in the proc signature.

**SystemVerilog:**
```systemverilog
module my_module (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic [7:0]  data_i,
    output logic [7:0]  data_o
);
    // ...
endmodule
```

**Anvil (compiler-verified):**
```
chan my_module_ch {
    left data_in  : (logic[8]@#1) @dyn - @#1,
    right data_out : (logic[8]@#1) @#data_in - @#data_in
}

proc my_module(ep : left my_module_ch) {
    loop {
        let d = recv ep.data_in >>
        send ep.data_out (d) >>
        cycle 1
    }
}
```

**Key differences:**
- Ports become channel endpoints — you CANNOT use bare types like `right (logic[8])` in a proc signature
- Every port group needs a `chan` definition first
- `clk_i` and `rst_ni` are removed (implicit in Anvil)
- Reset initialization happens through register defaults (Anvil regs initialize to 0)

### Top-Level Module with Submodule Instantiation

**SystemVerilog:**
```systemverilog
module top (input logic clk_i, input logic rst_ni);
    sub_module i_sub (.clk_i, .rst_ni, .data_i(my_data), .data_o(result));
endmodule
```

**Anvil (compiler-verified — see `03_channels.anvil`):**
```
proc Top() {
    chan ep_le -- ep_ri : foobar_ch;
    spawn Foo(ep_le);
    // Top uses ep_ri to communicate with Foo
}
```

Channel instantiation uses `chan left_ep -- right_ep : chan_class;`, then `spawn` replaces
module instantiation. Named port connections become channel endpoint passing.

---

## 2. Data Types

### Scalar and Vector Types

| SystemVerilog | Anvil | Notes |
|---|---|---|
| `logic` | `logic` | 1-bit signal |
| `logic [N-1:0]` | `logic[N]` | N-bit vector — Anvil uses width, not range |
| `logic [7:0]` | `logic[8]` | 8-bit example |
| `logic [31:0]` | `logic[32]` | 32-bit example |
| `reg [7:0] r` | `reg r : logic[8]` | Register declaration |
| `wire [7:0] w` | `let w = ...` | Wires become `let` bindings |

### Registers

**SystemVerilog:**
```systemverilog
reg [7:0] counter;
always_ff @(posedge clk_i or negedge rst_ni) begin
    if (~rst_ni) counter <= 8'd0;
    else         counter <= counter + 8'd1;
end
```

**Anvil (compiler-verified):**
```
reg counter : logic[8];
loop {
    set counter := *counter + 8'd1
}
```

- `reg name : type;` declares a register
- `*name` dereferences (reads) a register
- `set name := value` writes a register (takes 1 cycle)
- Reset is implicit — registers initialize to 0

### Arrays

**SystemVerilog:**
```systemverilog
logic [7:0] mem [0:3];   // 4-entry memory of 8-bit words
```

**Anvil (compiler-verified — see `05_generate.anvil`):**
```
type byte = (logic[8]);
reg mem : byte[4];
```

Array indexing: `*mem[i]` to read, `set mem[i] := value` to write.

### Structs

**SystemVerilog:**
```systemverilog
typedef struct packed {
    logic [3:0]  opcode;
    logic [7:0]  value;
} my_data_t;
```

**Anvil (compiler-verified — see `04_structs_enums_funcs.anvil`):**
```
struct my_data {
    opcode : (logic[4]),
    value : (logic[8])
}
```

- Commas between fields, NO trailing comma
- No `packed` keyword
- No `typedef` — structs are types directly

### Enums

**SystemVerilog:**
```systemverilog
typedef enum logic [1:0] {
    IDLE = 2'b00,
    RUN  = 2'b01,
    DONE = 2'b10
} state_t;
```

**Anvil (compiler-verified — see `04_structs_enums_funcs.anvil`):**
```
enum fsm_state {
    IDLE,
    RUN,
    DONE
}
```

- No explicit encoding — the compiler handles it
- Access variants as `fsm_state::IDLE`
- **Cannot do arithmetic on enums** — `*st + 2'd1` is invalid

### Type Aliases

**SystemVerilog:**
```systemverilog
typedef logic [7:0] byte_t;
```

**Anvil (compiler-verified):**
```
type byte = (logic[8]);
```

### Parameters and Localparams

**SystemVerilog:**
```systemverilog
module foo #(parameter WIDTH = 8) (...);
    localparam DEPTH = 2 ** WIDTH;
```

**Anvil:** Parameters are not directly supported as SV-style generics.
Use concrete values or channel-level parameterization. **Pseudocode:**
```
// No direct equivalent for SV parameters
// Use concrete types or define constants as comments
// Channel parameterization is limited — see 09_parameterized.anvil
```

**Important:** `CVA6Cfg.XLEN`, `$clog2()`, and package-qualified parameters
(`ariane_pkg::*`) have no Anvil equivalent. All values must be resolved to concrete
numbers.

---

## 3. Combinational Logic

### `assign` → `let` Binding

**SystemVerilog:**
```systemverilog
assign y = a & b;
assign z = sel ? a : b;
```

**Anvil (compiler-verified):**
```
let y = a & b;
let z = if (sel == 1'b1) { a } else { b };
```

- `let` bindings are Anvil's equivalent of continuous assignment
- Ternary operator `? :` becomes `if ... { } else { }`
- `let x = expr;` (semicolon) — parallel, computed alongside following code
- `let x = expr >>` (sequence operator) — sequential, must complete before next

### `always_comb` → `let` Bindings

**SystemVerilog:**
```systemverilog
always_comb begin
    case (sel)
        2'b00: y = a;
        2'b01: y = b;
        default: y = 8'd0;
    endcase
end
```

**Anvil (compiler-verified):**
```
let y = match (sel) {
    2'b00 => a,
    2'b01 => b,
    _     => 8'd0
};
```

### Write-Enable Decoder (Nested Combinational Logic)

**SystemVerilog (from `ariane_regfile_ff.sv`):**
```systemverilog
always_comb begin : we_decoder
    for (int j = 0; j < NrCommitPorts; j++) begin
        for (int i = 0; i < NUM_WORDS; i++) begin
            if (waddr_i[j] == i) we_dec[j][i] = we_i[j];
            else                 we_dec[j][i] = 1'b0;
        end
    end
end
```

**Anvil (from hand-written `ariane_regfile_ff.anvil`):** **pseudocode — uses SV params**
```
generate (j : 0, NrCommitPorts, 1) {
    generate (i : 0, NUM_WORDS, 1) {
        let we_dec[j][i] = if (waddr_i[j] == i) {
            we_i[j]
        } else {
            1'b0
        };
    }
}
```

---

## 4. Sequential Logic

### `always_ff` → `reg` + `set` + `loop`

Every `always_ff` block maps to a `loop` containing `set` expressions.

**SystemVerilog:**
```systemverilog
always_ff @(posedge clk_i or negedge rst_ni) begin
    if (~rst_ni) begin
        counter <= 8'd0;
        state   <= IDLE;
    end else begin
        counter <= counter + 8'd1;
        if (counter == 8'd255)
            state <= DONE;
    end
end
```

**Anvil (compiler-verified):**
```
reg counter : logic[8];
reg state : fsm_state;
loop {
    if (*counter == 8'd255) {
        set state := fsm_state::DONE;
        set counter := *counter + 8'd1
    } else {
        set counter := *counter + 8'd1
    }
}
```

**Critical rule:** Every loop path must take at least 1 cycle. A `set` takes 1 cycle.
A `cycle N` statement also advances time. A loop body with only `let` bindings and
`dprint` will fail compilation.

### Register with Enable

**SystemVerilog:**
```systemverilog
always_ff @(posedge clk_i) begin
    if (en) r <= d;
end
```

**Anvil (compiler-verified):**
```
reg en : logic;
reg d : logic[8];
reg r : logic[8];
loop {
    if (*en == 1'b1) {
        set r := *d
    } else {
        cycle 1
    }
}
```

Both branches must take at least 1 cycle — the `else { cycle 1 }` is required.

### Multiple Independent `always_ff` Blocks

In SV, you can have multiple `always_ff` blocks that run concurrently.
In Anvil, use multiple `loop` blocks within the same `proc`:

**Anvil (compiler-verified — see `02_registers_control.anvil`):**
```
proc Top() {
    reg counter : logic[8];
    // Loop 1: print messages
    loop {
        dprint "[Cycle %d] Hello" (*counter) >>
        cycle 1
    }
    // Loop 2: increment counter
    loop {
        set counter := *counter + 8'd1
    }
}
```

Multiple loops run concurrently within a process, like multiple `always` blocks.

---

## 5. Port Mapping

### SV Ports → Anvil Channels

This is **the most fundamental difference** between SV and Anvil. SV ports are bare
wires; Anvil ports are typed, lifetime-annotated channel endpoints.

**Step 1: Define a channel class** for each logical port group:
```
chan my_ch {
    left msg_name : (data_type @ lifetime) sync_pattern
}
```

**Step 2: Use channel endpoints** in proc signatures:
```
proc my_proc(ep : left my_ch) { ... }
```

**Step 3: Instantiate and connect** with `chan` + `spawn`:
```
chan ep_le -- ep_ri : my_ch;
spawn my_proc(ep_le);
// parent uses ep_ri
```

### Channel Message Anatomy

```
left msg_name : (logic[8]@#1) @dyn - @#1
│     │          │        │    │      │
│     │          │        │    │      └─ recv sync: within 1 cycle
│     │          │        │    └──────── send sync: dynamic (anytime)
│     │          │        └──────────── data lifetime: 1 cycle
│     │          └───────────────────── data type
│     └──────────────────────────────── message name
└────────────────────────────────────── direction (left/right)
```

### Common Sync Patterns

| Pattern | Meaning | Use Case |
|---|---|---|
| `@dyn - @#1` | Send anytime, recv within 1 cycle | Streaming data, fire-and-forget |
| `@#1 - @#1` | Send and recv each within 1 cycle | Lockstep synchronous |
| `@#req - @#req` | Synced to a named request message | Request-response protocols |
| `@dyn - @#1` with `@res` lifetime | Borrowed until response | Req/res with borrow checking |

### Request-Response Pattern

**SystemVerilog:**
```systemverilog
module server (
    input  logic [7:0] req_data_i,
    input  logic       req_valid_i,
    output logic [7:0] res_data_o,
    output logic       res_valid_o
);
```

**Anvil (compiler-verified — see `03_channels.anvil`):**
```
chan foobar_ch {
    left req : (logic[8]@res),
    right res : (logic[8]@#1)
}

proc Server(ep : left foobar_ch) {
    reg result : logic[8];
    loop {
        let x = recv ep.req >>
        set result := x + 8'd1 >>
        send ep.res (*result) >>
        cycle 1
    }
}
```

The `@res` lifetime on `req` means the sent value must remain stable until the
`res` message is sent back. This enforces protocol-level correctness.

---

## 6. Control Flow

### `case` → `match`

**SystemVerilog:**
```systemverilog
unique case (opcode)
    4'd0: result = a + b;
    4'd1: result = a - b;
    4'd2: result = a & b;
    default: result = 8'd0;
endcase
```

**Anvil (compiler-verified):**
```
match (*opcode) {
    4'd0 => dprint "ADD" (),
    4'd1 => dprint "SUB" (),
    4'd2 => dprint "AND" (),
    _    => dprint "UNKNOWN" ()
}
```

- `unique case` / `case` both become `match`
- `default` becomes `_`
- Arms use `=>` not `:`
- Arms separated by commas
- For multi-statement arms, use `{ ... }` blocks

### `if`/`else if`/`else`

**SystemVerilog:**
```systemverilog
if (a > b) result = a;
else if (a == b) result = 8'd0;
else result = b;
```

**Anvil (compiler-verified — see `04_structs_enums_funcs.anvil`):**
```
if (a > b) {
    dprint "a" ()
} else if (a == b) {
    dprint "equal" ()
} else {
    dprint "b" ()
}
```

### `inside` → `in`

**SystemVerilog:**
```systemverilog
if (opcode inside {4'd0, 4'd1, 4'd2})
```

**Anvil (compiler-verified — see `04_structs_enums_funcs.anvil`):**
```
if (*st in { fsm_state::IDLE, fsm_state::BUSY }) {
    // ...
}
```

### `for` / `generate` Loops

**SystemVerilog:**
```systemverilog
generate
    genvar k;
    for (k = 0; k < 4; k++) begin
        assign result[k] = data[3-k];
    end
endgenerate
```

**Anvil (compiler-verified — see `05_generate.anvil`):**
```
generate (i : 0, 3, 1) {
    set mem[i] := <(i)::logic[4]>
}
```

`generate (var : start, end, step) { body }` — end is inclusive.

**Important:** SV `for` loops inside `always_comb`/`always_ff` also map to `generate`
in Anvil.

---

## 7. Operators

### Bitwise and Logical

| SystemVerilog | Anvil | Notes |
|---|---|---|
| `a & b` | `a & b` | Bitwise AND |
| `a \| b` | `a \| b` | Bitwise OR |
| `a ^ b` | `a ^ b` | Bitwise XOR |
| `~a` | `~a` | Bitwise NOT |
| `a && b` | `a & b` | Logical AND (use bitwise for 1-bit) |
| `a \|\| b` | `a \| b` | Logical OR (use bitwise for 1-bit) |
| `!a` | `~a` | Logical NOT (use bitwise NOT) |

### Comparison

| SystemVerilog | Anvil | Notes |
|---|---|---|
| `a == b` | `a == b` | Equality |
| `a != b` | `a != b` | Inequality |
| `a > b` | `a > b` | Greater than |
| `a < b` | `a < b` | Less than |
| `a >= b` | `a >= b` | Greater or equal |
| `a <= b` | `a <= b` | Less or equal |

### Arithmetic

| SystemVerilog | Anvil | Notes |
|---|---|---|
| `a + b` | `a + b` | Addition |
| `a - b` | `a - b` | Subtraction |
| `a * b` | `a * b` | Multiplication |
| `a << n` | `a << n` | Left shift |
| `a >> n` | `a >> n` | Right shift |

### Concatenation

**SystemVerilog:**
```systemverilog
{a, b}           // Simple concatenation
{4{a}}           // Replication
{24'b0, data}    // Zero extension
```

**Anvil (compiler-verified — see `07_cast_concat.anvil`):**
```
#{*a, *b}        // Concatenation uses #{ } not { }
```

Replication (`{N{x}}`) has no direct Anvil equivalent — use explicit concatenation
or cast to a wider type.

### Casting / Type Conversion

**SystemVerilog:**
```systemverilog
logic [7:0] wide = {4'b0, narrow};   // Zero extend
logic [3:0] trunc = wide[3:0];       // Truncate
```

**Anvil (compiler-verified — see `07_cast_concat.anvil`):**
```
let wide = <(*a)::logic[8]>;     // Cast to wider type
let narrow = <(*a)::logic[2]>;   // Cast to narrower type (truncation)
```

Cast syntax: `<(expression)::target_type>` — parentheses around expression are required.

### Literal Formats

| SystemVerilog | Anvil | Notes |
|---|---|---|
| `8'd42` | `8'd42` | Decimal |
| `8'hFF` | `8'hFF` | Hex |
| `8'b1010_0101` | `8'b10100101` | Binary |
| `1'b0` | `1'b0` | Single bit |
| `'0` | `8'd0` (explicit width) | **`'0` is NOT valid Anvil** |
| `'1` | `8'hFF` (explicit width) | **`'1` is NOT valid Anvil** |

---

## 8. Common Pitfalls

These are mistakes the automated SV-to-Anvil converter consistently makes, based on
analysis in `anvil_ground_truth/report.md`.

### 8.1 Bare Types in Proc Endpoints (MOST COMMON)

**Wrong:**
```
proc foo(data_i : right (logic[32])) { ... }
```

**Right:**
```
chan data_ch {
    left data : (logic[32]@#1) @dyn - @#1
}
proc foo(ep : left data_ch) { ... }
```

Endpoints MUST reference channel classes, not bare data types.

### 8.2 SV Package Imports

**Wrong:**
```
// ariane_pkg::* — does not exist in Anvil
let x = CVA6Cfg.XLEN;  // Invalid
```

**Right:** Resolve all package-qualified names to concrete values before conversion.

### 8.3 `$clog2()` and System Functions

**Wrong:**
```
let width = $clog2(DEPTH);   // Not valid Anvil
```

**Right:** Precompute: if `DEPTH = 16`, use `4` directly.

### 8.4 Loops Without Time Advancement

**Wrong:**
```
loop {
    let x = *a & *b;
    dprint "result: %d" (x)
}
```

**Right:**
```
loop {
    let x = *a & *b;
    dprint "result: %d" (x) >>
    cycle 1
}
```

Every loop iteration must take at least 1 cycle (`set`, `cycle N`, or blocking
`send`/`recv` all count).

### 8.5 Using `let` Values After They Expire

**Wrong:**
```
let data = recv ep.res >>    // data valid for @#1 (1 cycle)
set counter := *counter + 8'd1 >>   // Takes 1 cycle — data expired!
dprint "data: %d" (data)    // ERROR: data no longer valid
```

**Right:**
```
let data = recv ep.res >>
dprint "data: %d" (data) >>    // Use BEFORE any cycle-consuming op
set counter := *counter + 8'd1
```

### 8.6 Mutating Borrowed Registers

**Wrong:**
```
send ep.req (*input) >>        // input is borrowed (@res lifetime)
set input := *input + 8'd1 >>  // MUTATES borrowed value!
let data = recv ep.res
```

**Right:**
```
send ep.req (*input) >>
let data = recv ep.res >>      // Wait for response FIRST
set input := *input + 8'd1     // THEN mutate
```

### 8.7 `'0` Literal

**Wrong:** `'0` — not valid Anvil syntax.

**Right:** Use width-qualified zeros: `8'd0`, `32'd0`, `1'b0`.

### 8.8 Combinational `let` Driving an Output

**Wrong:**
```
let is_accel_o = 1'b0;   // This doesn't drive an output port
```

**Right:** Outputs must go through `send` on a channel endpoint:
```
send ep.is_accel (1'b0) >>
```

---

## 9. Functions

**SystemVerilog:**
```systemverilog
function automatic logic [7:0] max(input logic [7:0] a, input logic [7:0] b);
    return (a > b) ? a : b;
endfunction
```

**Anvil (compiler-verified — see `04_structs_enums_funcs.anvil`):**
```
func max(a, b) {
    if a > b {
        a
    } else {
        b
    }
}
```

- No type annotations on parameters — types are inferred
- No `return` statement — the last expression is the return value
- Call with `call max(x, y)`, not `max(x, y)`

---

## 10. Non-Blocking Communication

**SystemVerilog** valid/ready handshakes map to Anvil's `try send`/`try recv`:

**Anvil (compiler-verified — see `08_try_send_recv.anvil`):**
```
try x = recv ep.req {
    // Got data: x is valid here
    dprint "Received: %d" (x)
} else {
    // No data available
    dprint "No request"
} >>
cycle 1
```

```
try send ep.res (1'd1) {
    dprint "Sent response"
} else {
    dprint "No receiver ready"
} >>
cycle 1
```

**Important:** Both branches of a `try` must still satisfy the 1-cycle-per-loop-path
rule. Add `>> cycle 1` after the try block.

---

## 11. Complete Examples

### Example 1: Combinational Decoder Stub

**SystemVerilog (`cva6_accel_first_pass_decoder`):**
```systemverilog
module cva6_accel_first_pass_decoder(
    input logic [31:0] instruction_i,
    output logic is_accel_o,
    output logic illegal_instr_o
);
    assign is_accel_o = 1'b0;
    assign illegal_instr_o = 1'b0;
endmodule
```

**Anvil (compiler-verified):**
```
chan decoder_ch {
    left instr : (logic[32]@#1) @dyn - @#1,
    right is_accel : (logic@#1) @#instr - @#instr,
    right illegal : (logic@#1) @#instr - @#instr
}

proc cva6_accel_first_pass_decoder(ep : left decoder_ch) {
    loop {
        let _instr = recv ep.instr >>
        send ep.is_accel (1'b0) >>
        send ep.illegal (1'b0) >>
        cycle 1
    }
}
```

### Example 2: FSM with State Register

**SystemVerilog:**
```systemverilog
module controller (
    input  logic       clk_i,
    input  logic       rst_ni,
    output logic [1:0] state_o
);
    typedef enum logic [1:0] { IDLE, LOAD, EXEC, DONE } state_t;
    state_t state_q, state_d;

    always_comb begin
        state_d = state_q;
        unique case (state_q)
            IDLE:  state_d = LOAD;
            LOAD:  state_d = EXEC;
            EXEC:  if (counter == 8'd10) state_d = DONE;
            DONE:  state_d = IDLE;
        endcase
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (~rst_ni) state_q <= IDLE;
        else         state_q <= state_d;
    end
endmodule
```

**Anvil (compiler-verified):**
```
enum fsm_state {
    IDLE,
    LOAD,
    EXEC,
    DONE
}

proc Controller() {
    reg state : fsm_state;
    reg counter : logic[8];
    loop {
        match (*state) {
            fsm_state::IDLE => {
                dprint "IDLE" () >>
                set state := fsm_state::LOAD
            },
            fsm_state::LOAD => {
                dprint "LOAD" () >>
                set state := fsm_state::EXEC
            },
            fsm_state::EXEC => {
                if (*counter == 8'd10) {
                    dprint "EXEC done" () >>
                    set state := fsm_state::DONE
                } else {
                    set counter := *counter + 8'd1
                }
            },
            _ => {
                dprint "DONE" () >>
                set state := fsm_state::IDLE
            }
        }
    }
}
```

**Key insight:** The SV pattern of separate `always_comb` (next-state logic) and
`always_ff` (register update) collapses into a single `loop` with `match` and `set`
in Anvil. The next-state value is directly written via `set`.

### Example 3: Producer-Consumer with Channels

**SystemVerilog (conceptual):**
```systemverilog
module producer (output logic [7:0] data_o, output logic valid_o);
    reg [7:0] val;
    always_ff @(posedge clk_i) begin
        val <= val + 8'd1;
        data_o <= val;
        valid_o <= 1'b1;
    end
endmodule

module consumer (input logic [7:0] data_i, input logic valid_i);
    always_ff @(posedge clk_i)
        if (valid_i) $display("Got: %d", data_i);
endmodule
```

**Anvil (compiler-verified — see `09_parameterized.anvil`):**
```
chan data_ch {
    left data : (logic[8]@#1) @dyn - @#1
}

proc Producer(ep : right data_ch) {
    reg val : logic[8];
    loop {
        send ep.data (*val) >>
        set val := *val + 8'd1
    }
}

proc Consumer(ep : left data_ch) {
    reg counter : logic[8];
    loop {
        let d = recv ep.data >>
        dprint "[Cycle %d] Received: %d" (*counter, d) >>
        cycle 1
    }
    loop {
        set counter := *counter + 8'd1
    }
}

proc Top() {
    chan ep_le -- ep_ri : data_ch;
    spawn Producer(ep_ri);
    spawn Consumer(ep_le);
    loop {
        cycle 10 >>
        dfinish
    }
}
```

---

## Quick Reference Card

| SV Construct | Anvil Equivalent |
|---|---|
| `module M(...)` | `proc M(ep : left chan_class)` |
| `input/output` ports | `chan` class + endpoint |
| `logic [N-1:0]` | `logic[N]` |
| `reg r` / `always_ff` | `reg r : type` + `set r := val` in `loop` |
| `wire w` / `assign` | `let w = expr` |
| `always_comb` | `let` bindings |
| `always_ff @(posedge clk)` | `loop { ... set ... }` |
| `if/else` | `if (...) { } else { }` |
| `case/unique case` | `match (...) { pat => expr, ... }` |
| `? :` (ternary) | `if (...) { a } else { b }` |
| `{a, b}` (concat) | `#{a, b}` |
| `$clog2(N)` | Precompute to constant |
| `inside {a, b}` | `in { a, b }` |
| `'0` | `N'd0` (explicit width) |
| `genvar` / `generate for` | `generate (i : start, end, step) { }` |
| `function` | `func name(args) { expr }` |
| function call | `call func_name(args)` |
| Module instantiation | `chan a -- b : ch; spawn Proc(a)` |
| Reset (`if (~rst_ni)`) | Implicit — regs init to 0 |
| `$display(...)` | `dprint "fmt" (args)` |
| `$finish` | `dfinish` |
