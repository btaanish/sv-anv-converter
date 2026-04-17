# Anvil Ground Truth — Compiler-Validated Syntax Report

**Author:** Iris
**Date:** 2026-04-17
**Issue:** #77

## Summary

9 Anvil files written from scratch, all compile successfully with `/opt/opam/default/bin/anvil -just-check`. This report documents ground-truth Anvil syntax based on actual compiler validation.

---

## 1. Compiler-Validated Examples

| File | Features Tested | Compiles? |
|------|----------------|-----------|
| `01_hello_world.anvil` | Minimal proc, reg, let, dprint, set, loop, >> | YES |
| `02_registers_control.anvil` | if-else, match, multiple loops, cycle delays | YES |
| `03_channels.anvil` | chan definition, send/recv, spawn, lifetime @res/@#1 | YES |
| `04_structs_enums_funcs.anvil` | struct, enum, type alias, func/call, `in` operator | YES |
| `05_generate.anvil` | generate, type alias, array reg, cast | YES |
| `06_sync_patterns.anvil` | Sync patterns @dyn-@#1, @#req-@#req | YES |
| `07_cast_concat.anvil` | Cast `<(expr)::type>`, concatenation `#{a,b}` | YES |
| `08_try_send_recv.anvil` | try send, try recv, non-blocking communication | YES |
| `09_parameterized.anvil` | Parameterized channel, multi-proc spawn | YES |

---

## 2. Critical Syntax Rules (Compiler-Verified)

### 2.1 Process Endpoints MUST Reference Channel Classes

**THIS IS THE #1 ISSUE WITH THE CONVERTER.**

**WRONG** (what the converter generates):
```
proc foo(data_i : right (logic[32])) { ... }
```

**RIGHT** (what the compiler accepts):
```
chan data_ch {
    left data : (logic[32]@#1) @dyn - @#1
}
proc foo(ep : left data_ch) { ... }
```

Endpoints reference channel classes, NOT bare data types. Every signal group needs a `chan` definition first.

### 2.2 Every Loop Path Must Take At Least 1 Cycle

**WRONG:**
```
loop {
    dprint "hello" (*counter)
}
```

**RIGHT:**
```
loop {
    dprint "hello" (*counter) >>
    cycle 1
}
```
Or use `set` (which itself takes 1 cycle):
```
loop {
    dprint "hello" (*counter) >>
    set counter := *counter + 8'd1
}
```

### 2.3 Borrow Checking — Values Must Live Long Enough

If a channel message has lifetime `@res`, the sent value must remain stable until the response message. You CANNOT modify the source register between send and recv.

**WRONG:**
```
send ep.req (*input) >>
set input := *input + 8'd1 >>   // Mutates borrowed register!
let data = recv ep.res
```

**RIGHT:**
```
send ep.req (*input) >>
let data = recv ep.res >>
dprint "got %d" (data) >>        // Use data BEFORE it expires
set input := *input + 8'd1       // Mutate AFTER response received
```

### 2.4 Let Bindings and Value Lifetimes

If a channel message has lifetime `@#1`, the received value is valid for only 1 cycle. You must use it immediately, before any `set` or `cycle` expressions.

**WRONG:**
```
let data = recv ep.res >>
set counter := *counter + 8'd1 >>  // Takes 1 cycle
dprint "data: %d" (data)           // data expired!
```

**RIGHT:**
```
let data = recv ep.res >>
dprint "data: %d" (data) >>       // Use immediately
set counter := *counter + 8'd1
```

### 2.5 Struct Syntax Uses Commas, Not Semicolons

```
struct my_struct {
    field1 : (logic[8]),
    field2 : (logic[16])
}
```
Note: commas between fields, NO trailing comma.

### 2.6 No Arithmetic on Enum Types

You cannot do `*st + 2'd1` where `st` is an enum. The compiler warns about invalid argument types.

### 2.7 Channel Data Types in Message Definitions

The data type in a channel message is written as `(data_type @ lifetime)`:
```
chan my_ch {
    left msg : (logic[8]@#1)
}
```
The `@lifetime` is INSIDE the parentheses with the type.

### 2.8 `let` Bindings Are Parallel Unless Sequenced

`let x = expr; body` — parallel (x computed alongside body)
`let x = expr >> body` — sequential (x computed, then body starts)

A `let` binding with `;` that is never awaited generates a warning.

### 2.9 Cast Syntax

```
<(expression)::target_type>
```
The expression MUST be in parentheses inside the angle brackets.

### 2.10 Concatenation Syntax

```
#{expr1, expr2, ..., exprN}
```
NOT `{expr1, expr2}` (SystemVerilog style).

---

## 3. Analysis of Converter Output Failures

### 3.1 Fundamental Architecture Problem

The converter treats Anvil as "SystemVerilog with different keywords." This is fundamentally wrong. Anvil is a **channel-oriented, process-based** language. The key issues:

1. **No channel class definitions** — The converter maps SV ports directly to proc endpoints with bare types like `(logic[32])`. Anvil requires `chan` definitions that specify message types, lifetimes, and sync patterns.

2. **SV-style parameters** — `CVA6Cfg.XLEN` is not valid Anvil. Parameters must be declared as `<N : int>` in channel/proc definitions.

3. **Package imports** — `ariane_pkg::*` has no Anvil equivalent. All types must be defined inline or imported through Anvil's own mechanisms.

4. **`$clog2()` calls** — Not valid Anvil syntax.

5. **`inside` operator** — Anvil uses `in { ... }` not `inside #{ ... }`.

6. **Combinational `let` as output** — `let is_accel_o = 1'b0;` doesn't drive an output. In Anvil, outputs go through `send` on a channel endpoint.

7. **`'0` literal** — Not valid Anvil. Use explicit zero literals like `8'd0`.

### 3.2 What a Correct Conversion Would Look Like

For a simple stub module like `cva6_accel_first_pass_decoder`:

**SV:**
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

**Correct Anvil:**
```
chan decoder_in_ch {
    left instr : (logic[32]@#1) @#1 - @#1
}
chan decoder_out_ch {
    left is_accel : (logic@#1) @#1 - @#1,
    left illegal : (logic@#1) @#1 - @#1
}
proc cva6_accel_first_pass_decoder(
    in_ep : left decoder_in_ch,
    out_ep : right decoder_out_ch
) {
    loop {
        let instr = recv in_ep.instr;
        send out_ep.is_accel (1'b0);
        send out_ep.illegal (1'b0) >>
        cycle 1
    }
}
```

---

## 4. Lessons Learned During Compile Testing

| Attempt | Error | Root Cause | Fix |
|---------|-------|-----------|-----|
| Channel send after delay | "Value does not live long enough" | `recv` value with `@res` lifetime expired after `cycle 2` | Store in register before delay |
| Enum arithmetic | "Invalid argument types" | Can't add integer to enum | Don't use arithmetic on enums |
| Let without await | "Value bound to m is potentially not awaited" | `let m = expr;` in parallel but `m` never used in awaited context | Use `let m = expr >>` (sequential) |
| Loop without cycle | "All paths must take at least one cycle" | Combinational-only loop body | Add `>> cycle 1` or `>> set ...` |
| Bare type as endpoint | "Syntax error" | Proc endpoint must be `chan_class`, not `(logic[N])` | Define a `chan` class first |
| try send/recv zero-cycle path | "Recurse delay must be greater than 0" | Both branches of try completed in 0 cycles | Add `>> cycle 1` after the if/else |
| Parameterized type mismatch | "expected Tuple but got Array" | Channel type `(logic[W])` with param `W` | Use concrete types or match exactly |

---

## 5. Minimal Working Patterns for Common SV Constructs

### Counter (SV: `always_ff @(posedge clk) counter <= counter + 1`)
```
proc Counter() {
    reg counter : logic[8];
    loop {
        set counter := *counter + 8'd1
    }
}
```

### Combinational Logic (SV: `assign y = a & b`)
```
// Must be inside a loop that sends/receives via channels
loop {
    let a = recv ep_in.a;
    let b = recv ep_in.b;
    let y = a & b;
    send ep_out.y (y) >>
    cycle 1
}
```

### Mux (SV: `assign y = sel ? a : b`)
```
let y = if sel == 1'b1 { a } else { b };
```

### Register with Enable (SV: `if (en) r <= d`)
```
loop {
    if (*en == 1'b1) {
        set r := *d
    } else {
        cycle 1
    }
}
```

### Bit Slice (SV: `a[7:0]`)
```
// Anvil uses array indexing: a[0+:8] syntax TBD
// Cast/truncation: <(*a)::logic[8]>
```

---

## 6. Recommendations for Converter Rewrite

1. **Define channel classes for every port group** — Group related SV inputs/outputs into channel messages with appropriate lifetimes
2. **Map `always_ff` blocks to `reg` + `set` inside loops** — Each always block becomes a loop thread
3. **Map `always_comb`/`assign` to `let` bindings** — Within appropriate loop context
4. **Remove all SV-isms** — No `$clog2`, `inside`, `'0`, package imports
5. **Every loop must advance time** — At minimum `cycle 1` or a `set` expression
6. **Handle lifetimes explicitly** — Determine sync patterns based on how values are used across module boundaries
7. **Use concrete types** — Avoid parameterized types initially; get concrete versions compiling first
