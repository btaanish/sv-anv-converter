# Anvil Semantic Correctness Audit Report

**Author:** Iris
**Date:** 2026-04-22
**Issue:** tbc-db #2

---

## 1. Executive Summary

Audited 5 target converted Anvil files: `alu.anvil`, `decoder.anvil`, `cva6_accel_first_pass_decoder.anvil`, `scoreboard.anvil`, `issue_stage.anvil`. All 5 compile successfully with `anvil -just-check` and produce valid SystemVerilog via full compilation. However, **semantic correctness varies significantly** across files. The decoder is the strongest translation; the ALU and issue_stage have the most semantic gaps.

**Overall assessment:** ~60% real translation, ~30% partial stub, ~10% pure stub (by logic coverage of original SV behavior).

---

## 2. Per-File Audit

### 2.1 alu.anvil

**Compile status:** PASS (no warnings)
**Classification:** PARTIAL STUB

**Positive:**
- Proper `chan` definitions with correct syntax (`alu_in_ch`, `alu_cpop_ch`, `alu_out_ch`)
- Correct use of `left`/`right` endpoint directions
- Input staging via recv -> set register pattern is valid
- Separate recv loop and compute loop (correct Anvil process structure)
- Loop bodies all advance time (via `set` or `cycle 1`)

**Semantic Issues:**
1. **[CRITICAL] Only ADD operation implemented.** The ALU computes `op_a + op_b` regardless of the `operation` input. The original SV ALU supports ~20+ operations (ADD, SUB, AND, OR, XOR, SRA, SRL, SLL, comparisons, etc.). The `operation` register is received but never read in the compute loop.
2. **[CRITICAL] Branch resolution hardcoded to 0.** Original SV computes branch taken/not-taken based on comparison results. This is stubbed to `1'b0`.
3. **[MAJOR] RVB/ZKN/RVZiCond paths omitted** (acknowledged in comments). These are real hardware features missing from the model.
4. **[MAJOR] `fu_data_t` struct flattened.** The original uses a struct; here individual signals are used. This changes the communication pattern semantically.
5. **[MINOR] Two parallel loops sharing registers.** The recv loop writes `r_op_a`, `r_op_b`, etc., while the compute loop reads them. In Anvil's concurrent model this creates a race between input staging and output computation. The compiled SV shows these as separate threads with independent event scheduling, meaning the compute loop may read stale register values (from the previous cycle's recv, not the current one). This is actually correct for modeling registered pipeline stages, but differs from the original SV which is purely combinational.
6. **[MINOR] cpop input received but never used in computation.**

**Compiled SV semantic comparison:**
The compiled SV produces `_out_result_0 = r_op_a_q + r_op_b_q` (line 120 of compiled output), confirming the ALU is a simple adder. The original SV ALU is a full arithmetic/logic unit with operation muxing. **Semantically incorrect.**

**Verdict:** Structurally valid Anvil, but models <10% of original ALU behavior.

---

### 2.2 decoder.anvil

**Compile status:** PASS (4 warnings about non-constant offset for `r_irq_mideleg`)
**Classification:** REAL TRANSLATION

**Positive:**
- Comprehensive channel definitions for all 37 input signals and 23 output signals
- Full opcode decode tables for: OpcodeSystem, OpcodeMiscMem, OpcodeOp, OpcodeOp32, OpcodeOpImm, OpcodeOpImm32, OpcodeStore, OpcodeLoad, OpcodeStoreFp, OpcodeLoadFp, OpcodeMadd/Msub/Nmsub/Nmadd, OpcodeOpFp, OpcodeAmo, OpcodeBranch, OpcodeJalr
- Correct mapping of opcode -> functional unit (fu) and opcode -> operation (op)
- Proper `funct10` construction via shift and OR
- Illegal instruction detection with privilege-level checks
- ECALL/EBREAK detection
- Exception cause computation with priority (debug > interrupt > exception)
- Interrupt priority chain (M_EXT > M_SW > M_TIMER > S_EXT > S_SW > S_TIMER)
- Interrupt delegation logic with SIE/privilege checks
- Immediate select logic with all 7 immediate types

**Semantic Issues:**
1. **[MINOR] Vectorial FP, Bitmanip, Hypervisor, CVXIF, Accelerator, CBO, ZKN, ZiCond paths omitted** (acknowledged). These are disabled in the concrete parameter set (RVB=0, RVH=0, CvxifEn=0, etc.), so omitting them is **semantically correct** for this configuration.
2. **[MINOR] `funct10` computation may differ from SV.** The Anvil code computes `(f7 << 3) | f3` as a 10-bit value. The original SV concatenates `{funct7, funct3}` which is equivalent. However, the shift-OR approach is fragile if widths change.
3. **[WARNING] Non-constant index into `r_irq_mideleg`.** The compiler warns about this. The code `*r_irq_mideleg[<(irq_cause)::logic[6]>]` uses a dynamic bit select. This compiles but borrows the full register range, which is semantically safe but may generate less optimal hardware.
4. **[MINOR] Sequential recv of 37 individual signals** adds significant latency (37 cycles per input set in the recv loop, since each `recv >> set` pair takes a cycle). The original SV decoder is purely combinational. This is an inherent limitation of the channel-per-signal approach.
5. **[MINOR] JAL (opcode 111) decode sends fu=CTRL_FLOW (4'd2) but no operation code** — the op mapping falls through to the final `else { 8'd0 }` (ADD). Should be JALR-like operation.

**Compiled SV semantic comparison:**
The compiled SV generates a massive combinational decode tree matching the if/else chains. The logic correctly maps opcodes to functional units and operations. The interrupt priority chain compiles to correct priority logic. **Semantically correct for the configured parameter set.**

**Verdict:** Strong translation. The most complete and semantically faithful of the 5 audited files.

---

### 2.3 cva6_accel_first_pass_decoder.anvil

**Compile status:** PASS (no warnings)
**Classification:** PURE STUB (intentionally)

**Positive:**
- Correct `chan` definitions
- Proper endpoint directions
- Loop advances time via `cycle 1`
- Clean, minimal structure

**Semantic Issues:**
1. **[INFO] All outputs hardcoded to 0.** `is_accel_o=0`, `instruction_o=0`, `illegal_instr_o=0`, `is_control_flow_instr_o=0`. This matches the original SV which is also a stub (`assign is_accel_o = 1'b0; assign illegal_instr_o = 1'b0`).
2. **[MINOR] Inputs not consumed.** The `in_ep` endpoint is declared but never recv'd from. The Anvil process ignores `instruction_i`, `fs_i`, and `vs_i`. The compiled SV confirms the input ack signals are never asserted — the module never acknowledges inputs.
3. **[MINOR] Extra outputs.** The Anvil version has `instruction_o` (64-bit) and `is_control_flow_instr_o` which may not exist in the simplest SV stub. This suggests it was converted from a slightly different version of the SV (with `EnableAccelerator` parameter).

**Compiled SV semantic comparison:**
All outputs are `localparam` constants (0). The event scheduling machinery sequences the sends but the data is always constant. **Semantically correct** — the original SV is also a constant-output stub.

**Verdict:** Correct stub translation. Matches original SV semantics perfectly (both are no-ops).

---

### 2.4 scoreboard.anvil

**Compile status:** PASS (no warnings)
**Classification:** PARTIAL STUB

**Positive:**
- Proper channel definitions for 15 inputs and 17 outputs
- State registers: `mem_issued`, `mem_cancelled`, `mem_valid` (8-bit each for 8 SB entries)
- Pointer tracking: `issue_ptr`, `commit_ptr_0`, `commit_ptr_1`
- Flush logic: resets all state and pointers
- Issue logic: advances `issue_ptr` when valid instruction acknowledged
- Commit pointer advancement with dual commit port support
- Snapshot registers for cross-thread register sharing (correct Anvil pattern)

**Semantic Issues:**
1. **[CRITICAL] Scoreboard entries are not actually stored.** The original SV maintains an array of `scoreboard_entry_t` structs (8 entries). The Anvil version only tracks `mem_issued`, `mem_cancelled`, `mem_valid` bitmasks — it never stores the actual instruction data in per-entry slots.
2. **[CRITICAL] `commit_instr_0` and `commit_instr_1` outputs are hardcoded to `64'd0`.** The original SV reads committed instruction data from the scoreboard entry array. Since entries aren't stored, there's nothing to read.
3. **[CRITICAL] `commit_drop_0` and `commit_drop_1` hardcoded to `1'b0`.** The original SV computes drop based on speculative execution state.
4. **[CRITICAL] `fwd_wb_data` hardcoded to `256'd0`.** Forwarding data should come from writeback ports. Without per-entry storage, forwarding is impossible.
5. **[MAJOR] `mem_issued` bitmask is never actually updated by issue or writeback.** The state update loop advances pointers but never sets bits in `mem_issued`, `mem_cancelled`, or `mem_valid`. The "full" check (`s_issued == 8'hFF`) will always be false since `mem_issued` stays 0.
6. **[MAJOR] Writeback handling missing.** The original SV updates entries when writeback valid signals fire. The Anvil version receives `wt_valid`, `x_we`, `x_rd` but never acts on them.
7. **[MINOR] Commit pointer arithmetic.** `commit_ptr_1 := s_cp0 + num_commit + 3'd1` — this always keeps `commit_ptr_1 = commit_ptr_0 + 1`, which is correct for NrCommitPorts=2.

**Compiled SV semantic comparison:**
The compiled SV shows the pointer advancement logic works correctly in isolation, but the scoreboard entries are never populated. The outputs that depend on entry data are constant zeros. **Semantically incomplete** — the skeleton is correct but the core data-storage functionality is missing.

**Verdict:** Has the right shape but ~30% of original behavior. Issue/commit pointer management works; entry storage, forwarding, and writeback are absent.

---

### 2.5 issue_stage.anvil

**Compile status:** PASS (no warnings)
**Classification:** PARTIAL STUB (structural wrapper)

**Positive:**
- Correct multi-channel design (4 channels: `is_in_ch`, `is_wb_ch`, `is_out_main_ch`, `is_out_extra_ch`)
- Dual recv loops for independent input groups (decode inputs and writeback inputs)
- Dual output loops for main and extra outputs
- `issue_instr_hs` handshake computation: `*issue_valid_sb & *issue_ack_iro`

**Semantic Issues:**
1. **[CRITICAL] Submodule instantiation missing.** The original SV `issue_stage` instantiates `scoreboard` and `issue_read_operands` as submodules. The Anvil version models their outputs as opaque registers (`sb_full_r`, `decoded_ack_r`, `fu_data_r`, etc.) that are **never written to**. All these registers default to 0 and stay 0 forever.
2. **[CRITICAL] No `spawn` of sub-processes.** Anvil's mechanism for submodule instantiation is `spawn`. The issue_stage should `spawn scoreboard(...)` and `spawn issue_read_operands(...)` with appropriate channel connections. Without spawning, the module is a pass-through of zero-initialized registers.
3. **[CRITICAL] All "submodule output" registers are dead.** 37 registers (lines 130-170) are declared but never set. Every output from `out_main` and `out_extra` that reads these registers produces 0.
4. **[MAJOR] Internal wiring registers (`issue_instr_sb`, `issue_valid_sb`, `issue_ack_iro`) are never written.** These should be driven by the scoreboard subprocess.
5. **[MINOR] The recv loops correctly separate decode-path and writeback-path inputs, which matches the original SV's port grouping.** This is good structural preservation.

**Compiled SV semantic comparison:**
All submodule-dependent outputs compile to constant 0. The input recv/staging logic works correctly. **Semantically a skeleton** — correct channel structure, but no internal computation.

**Verdict:** Pure structural wrapper with no submodule instantiation. ~5% of original behavior (only input staging and output routing).

---

## 3. Cross-Cutting Semantic Issues

### 3.1 Channel-Per-Signal Anti-Pattern

All 5 files define one channel message per SV port signal. For example, `decoder_in_ch` has 37 separate `left` messages, each requiring its own `recv >> set` in the loop body. This creates:

- **Latency inflation:** The recv loop takes N cycles to receive N signals (sequentially). The original SV processes all inputs combinationally in 0 cycles.
- **Port explosion in compiled SV:** Each channel message generates `_valid`, `_ack`, and `_data` wires. The scoreboard's compiled SV has 100+ port signals vs ~30 in the original.
- **Missed struct opportunities:** Anvil supports `struct` types. Grouping related signals (e.g., all of `fu_data_t` fields, all exception fields) into structs within a single channel message would be more faithful and efficient.

**Recommendation:** Use Anvil structs and fewer channel messages. For example:
```
struct decoded_instr_t {
    pc : (logic[64]),
    opcode : (logic[7]),
    rd : (logic[5]),
    funct3 : (logic[3]),
    ...
}
chan decoder_in_ch {
    left instr : (decoded_instr_t @#1) @#1 - @#1
}
```

### 3.2 Sync Pattern `@dyn - @dyn` Everywhere

Every channel in all 5 files uses `@dyn - @dyn` sync pattern. This is the most general (latency-insensitive) pattern, generating full valid/ack handshaking in compiled SV. However:

- For pipeline stages that communicate every cycle, `@#1 - @#1` would be more appropriate, eliminating handshake overhead and more faithfully modeling the original SV's cycle-accurate behavior.
- The original SV modules are combinational or single-cycle registered — they don't need handshaking.

### 3.3 Two-Loop Pattern (recv + compute)

All hand-written files use a two-loop pattern: one loop receives all inputs into staging registers, another loop computes and sends outputs. This introduces a 1-cycle latency between input arrival and output computation that doesn't exist in the original SV. For combinational modules (like the decoder or ALU), this is semantically incorrect — the original produces outputs in the same cycle as inputs.

### 3.4 Register Reads in Compute Loop

Reading registers with `*r_foo` in the compute loop reads the value from the **previous** cycle's set (since `set` takes effect next cycle). This is correct for modeling registered pipeline stages but incorrect for modeling combinational logic. The decoder, for example, should ideally use `let` bindings from `recv` directly, not staging registers.

---

## 4. Summary Statistics

| File | Compiles | Classification | Logic Coverage | Key Missing |
|------|----------|---------------|---------------|-------------|
| alu.anvil | YES | Partial Stub | ~10% | Operation mux, branch resolution |
| decoder.anvil | YES (4 warn) | Real Translation | ~85% | VFP/Bitmanip (disabled params) |
| cva6_accel_first_pass_decoder.anvil | YES | Pure Stub (correct) | 100% | N/A (original is also stub) |
| scoreboard.anvil | YES | Partial Stub | ~30% | Entry storage, forwarding, writeback |
| issue_stage.anvil | YES | Partial Stub | ~5% | Submodule spawn, all computation |

**Overall: 1 real translation, 1 correct stub, 3 partial stubs.**

### Broader Sample (from 10-file sample of converted/ directory):
- ~80% of hand-written files are real translations with substantial logic
- ~11% of all files (50/445) contain [MANUAL-CLEANUP-NEEDED] tags
- Auto-generated files (from `sv2anvil.py`) are predominantly stubs
- 445 total .anvil files in converted/

---

## 5. Main Categories of Semantic Issues

1. **Missing operation dispatch** (ALU, scoreboard) — Code receives control signals but doesn't act on them
2. **Missing submodule instantiation** (issue_stage) — No `spawn`, submodule outputs modeled as dead registers
3. **Missing state storage** (scoreboard) — Bitmask tracking without actual data arrays
4. **Latency mismatch** — All files add 1+ cycle latency vs original combinational SV
5. **Channel granularity** — One message per signal instead of struct-based grouping
6. **Uniform `@dyn-@dyn` sync** — Unnecessary handshaking overhead for fixed-latency pipelines

---

## 6. Recommendations

1. **decoder.anvil is production-quality** for its parameter configuration. Only needs JAL operation fix and struct consolidation for optimization.
2. **alu.anvil needs operation mux implementation** — the decode table from decoder.anvil shows all operation codes; the ALU should match/mux on them.
3. **scoreboard.anvil needs entry array storage** — use `reg` arrays and implement the actual issue/writeback/commit data flow.
4. **issue_stage.anvil needs `spawn`** — this is the highest-priority fix; without submodule instantiation, the module is non-functional.
5. **All files should migrate from `@dyn-@dyn` to `@#1-@#1`** for pipeline-stage channels to eliminate unnecessary handshaking.
6. **Group signals into structs** to reduce channel message count and match SV port groupings.
