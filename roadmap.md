# Roadmap — BOOM/Rocket/CVA6 to Anvil Conversion

## Project Goal
Convert three RISC-V processor implementations (BOOM, Rocket Chip, CVA6) from their source HDL to Anvil, then verify equivalence by compiling Anvil back to SystemVerilog.

## Course Corrections

### 2026-04-17 (early): All 27 .anvil files failed to compile
Root causes: regex-based converter, no compiler validation, wrong Anvil semantics. Led to M3.

### 2026-04-17 (late): M3 complete, converter improved to 8/43 pass rate
AST-based converter rewrite (Maya), hand-written references (Dana, Leo), mapping guide (Finn).
Remaining 35 failures: 17 undefined-identifier (cross-scope let bindings), 6 syntax errors (! and $ chars), 3 type mismatches.

## Milestones

### M1: Research & Foundation (budget: 4 impl cycles)
**Status:** COMPLETE (but output quality invalidated — see course correction above)

### M1.1–M2.2: Previous conversion batches
**Status:** INVALIDATED — all 27 .anvil files fail to compile. Code exists but is syntactically wrong.

### M3: Anvil Compiler Validation & Reference Conversion (budget: 8 cycles)
**Status:** COMPLETE ✓
**Results:**
- 2 hand-written modules compile (decoder_stub, regfile_ff)
- sv2anvil.py rewritten as AST-based (Lexer→Parser→IR→Codegen)
- Mapping guide at docs/sv_to_anvil_mapping.md
- Converter passes 8/43 CVA6 core modules (alu, aes, alu_wrapper, ariane_regfile_ff, compressed_decoder, cva6_accel_first_pass_decoder_stub, cvxif_compressed_if_driver, cvxif_fu)
- 9 ground-truth Anvil examples in anvil_ground_truth/examples/

### M4: Fix Converter & Achieve 43/43 CVA6 Core Compilation (budget: 8 cycles) — CURRENT
**Status:** NOT STARTED
**Goal:** Fix sv2anvil.py to handle remaining 35 failing modules and produce compilable output for all 43 CVA6 core modules. Two parallel tracks:
1. **Converter fixes:** Fix the 3 error categories — undefined identifiers (cross-scope let→reg promotion), syntax errors (! → ~, $ removal), type mismatches
2. **Manual fixes:** For modules the converter can't fully handle, hand-fix the output
**Acceptance criteria:** All 43 files in converted/ pass `anvil -just-check` with exit code 0

### M5: CVA6 Subdirectories (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert frontend/, cache_subsystem/, cva6_mmu/, pmp/, cvxif_example/, include/ packages.

### M6: BOOM Conversion (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert BOOM to Anvil. Chisel-based, needs Chisel→SV→Anvil pipeline.

### M7: Rocket Chip Conversion (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert Rocket Chip to Anvil. Chisel-based, largest codebase.

### M8: Validation & Polish (budget: TBD)
**Status:** NOT STARTED
**Goal:** Full round-trip verification. Compile Anvil→SV, compare with originals.

## Lessons Learned
- **CRITICAL: Always compile-check output.** The team produced 27 files over many cycles without ever running the compiler. ALL were invalid. Verification MUST include `anvil -just-check` on every file.
- **Understand the target language deeply before converting.** Anvil is fundamentally different from SV — it uses channels, send/recv, lifetimes, not ports. A superficial syntax mapping is insufficient.
- **Regex-based conversion is insufficient.** Human feedback confirmed: need a proper parser that understands SV AST and maps it to Anvil semantics, not just syntax.
- **Previous lessons still apply:** 1 module per worker, parallel conversion + sequential verification, scale workers for throughput.
- **Planning budget:** 3 Athena cycles for M1 planning was too many. Target 1 cycle for future milestones.
- **Manual conversion >> auto conversion:** This is even more true now. Need reference manual conversions before automating.
- **Cross-scope variable references are the #1 converter issue.** SV `always_comb` assigns variables used in `always_ff`. Anvil `let` bindings are scoped — converter must promote these to `reg` or restructure scopes.
- **Anvil negation is `~`, not `!`.** The converter must translate SV `!` to Anvil `~` for logical negation.

## Progress Tracking
- CVA6 top-level core: 8/43 compile from converter, 2/43 hand-written compile (10 total compiling)
- CVA6 subdirectories: 0/~71 converted (0%)
- BOOM: not started
- Rocket Chip: not started

## Research Findings
- CVA6 = native SV (42K LOC), best first target (moderate complexity, clean modules)
- BOOM = Chisel (38K LOC), needs Chisel→Verilog→Anvil pipeline
- Rocket Chip = Chisel (55K LOC), largest/most complex, SoC generator
- Anvil: process-oriented HDL, channels with lifetimes, implicit clk/rst
- Anvil toolchain available at `/opt/opam/default/bin/anvil`
- Anvil key concepts: proc (not module), chan (channels with left/right endpoints), send/recv, reg + set, let bindings, loop, generate/generate_seq, >> (sequence), ; (parallel join)
