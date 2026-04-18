# Roadmap — BOOM/Rocket/CVA6 to Anvil Conversion

## Project Goal
Convert three RISC-V processor implementations (BOOM, Rocket Chip, CVA6) from their source HDL to Anvil, then verify equivalence by compiling Anvil back to SystemVerilog.

## Course Corrections

### 2026-04-17 (early): All 27 .anvil files failed to compile
Root causes: regex-based converter, no compiler validation, wrong Anvil semantics. Led to M3.

### 2026-04-17 (late): M3 complete, converter improved to 8/43 pass rate
AST-based converter rewrite (Maya), hand-written references (Dana, Leo), mapping guide (Finn).
Remaining 35 failures: 17 undefined-identifier (cross-scope let bindings), 6 syntax errors (! and $ chars), 3 type mismatches.

### 2026-04-18: M4 complete — 43/43 CVA6 core compile
Ares's team achieved full compilation of all 43 CVA6 core modules. Independently verified by Athena. Converter at 2243 lines (AST-based). However, converter only passes ~33% of non-core CVA6 files — additional patterns needed.

### 2026-04-18: M5 complete — 82/82 CVA6 non-vendor files compile
39 utility+SoC files converted. Apollo verified: all compile, but semantic spot-checks revealed some files are port-level stubs (clint, sram, rv_tracer, ariane_verilog_wrap). Converter improved to ~55% on vendor files.

## Milestones

### M1: Research & Foundation (budget: 4 impl cycles)
**Status:** COMPLETE

### M1.1–M2.2: Previous conversion batches
**Status:** INVALIDATED — superseded by M3/M4

### M3: Anvil Compiler Validation & Reference Conversion (budget: 8 cycles)
**Status:** COMPLETE ✓

### M4: Fix Converter & Achieve 43/43 CVA6 Core Compilation (budget: 8 cycles)
**Status:** COMPLETE ✓ (verified 2026-04-18)
**Results:** All 43 CVA6 core .anvil files in converted/ pass `anvil -just-check`

### M5: CVA6 Utility & SoC Integration Modules (budget: 8 cycles, used: 6)
**Status:** COMPLETE ✓ (verified 2026-04-18)
**Results:** 39/39 .anvil files compile. Semantic quality mixed — clint, sram, rv_tracer, ariane_verilog_wrap are stubs. Quality fixes deferred to M9.

### M6: CVA6 Vendor Files — PULP Platform (budget: 10 cycles)
**Status:** IN PROGRESS
**Scope:** Convert 153 vendor/pulp-platform .sv files:
- common_cells/ (74 files): FIFOs, CDCs, arbiters, synchronizers
- axi/ (36 files): AXI infrastructure (mux, demux, CDC, burst splitter)
- fpga-support/ (21 files): FPGA primitives
- tech_cells_generic/ (15 files): technology cell wrappers
- axi_riscv_atomics/ (7 files): AXI atomic operations
**Converter baseline:** ~55% pass rate on vendor files (11/20 sampled)
**Approach:** Improve converter for remaining patterns, batch-convert, hand-fix failures
**Acceptance criteria:** All 153 .anvil files pass `anvil -just-check` with exit code 0

### M7: BOOM Conversion (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert BOOM to Anvil. Chisel-based, needs Chisel→SV→Anvil pipeline.

### M8: Rocket Chip Conversion (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert Rocket Chip to Anvil. Chisel-based, largest codebase.

### M9: Validation & Polish (budget: TBD)
**Status:** NOT STARTED
**Goal:** Full round-trip verification. Compile Anvil→SV, compare with originals. Fix semantic stubs from M5.

## Lessons Learned
- **CRITICAL: Always compile-check output.** The team produced 27 files over many cycles without ever running the compiler. ALL were invalid. Verification MUST include `anvil -just-check` on every file.
- **Understand the target language deeply before converting.** Anvil is fundamentally different from SV — it uses channels, send/recv, lifetimes, not ports. A superficial syntax mapping is insufficient.
- **Regex-based conversion is insufficient.** Human feedback confirmed: need a proper parser that understands SV AST and maps it to Anvil semantics, not just syntax.
- **Previous lessons still apply:** 1 module per worker, parallel conversion + sequential verification, scale workers for throughput.
- **Planning budget:** Target 1 cycle for milestone planning.
- **Manual conversion >> auto conversion:** Need reference manual conversions before automating.
- **Cross-scope variable references are the #1 converter issue.** SV `always_comb` assigns variables used in `always_ff`. Anvil `let` bindings are scoped — converter must promote these to `reg` or restructure scopes.
- **Anvil negation is `~`, not `!`.** The converter must translate SV `!` to Anvil `~` for logical negation.
- **Converter generalization needed.** 43/43 core pass rate doesn't transfer — non-core files have interfaces, packages, generate blocks that the converter doesn't handle yet (~33% pass rate on non-core).
- **Stub files pass compilation but lack semantics.** Several M5 files were port-level skeletons. Acceptance criteria should require semantic spot-checks, not just compilation.
- **Scale workers per file count.** 153 vendor files needs many parallel workers to avoid timeout. Assign ~5-10 files per worker max.

## Progress Tracking
- CVA6 core: 43/43 compile ✓
- CVA6 utility+SoC: 39/39 compile ✓
- CVA6 vendor: 0/153 (M6 starting)
- CVA6 testbench/verif: 0/~116 (low priority)
- BOOM: not started
- Rocket Chip: not started
- Total converted: 82 files

## Research Findings
- CVA6 = native SV (42K LOC), best first target (moderate complexity, clean modules)
- BOOM = Chisel (38K LOC), needs Chisel→Verilog→Anvil pipeline
- Rocket Chip = Chisel (55K LOC), largest/most complex, SoC generator
- Anvil: process-oriented HDL, channels with lifetimes, implicit clk/rst
- Anvil toolchain available at `/opt/opam/default/bin/anvil`
- Anvil key concepts: proc (not module), chan (channels with left/right endpoints), send/recv, reg + set, let bindings, loop, generate/generate_seq, >> (sequence), ; (parallel join)
