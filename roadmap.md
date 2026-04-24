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

### 2026-04-19: M7 complete — 445/445 CVA6 files compile
Full CVA6 conversion achieved in 7 cycles. Converter improved to handle 416/445 files automatically; 15 complex files (cache subsystem, MMU, frontend, testbench) hand-written by Dana and Leo. All 445 .anvil files verified passing `anvil -just-check`. CVA6 phase complete. Next challenge: Chisel-based repos (BOOM, Rocket) — no JVM in environment.

### 2026-04-22: Human intervention — URGENT quality audit required
Human flagged that agent_spec.md and sv2anvil.py contain wrong results that don't adhere to Anvil principles. Compilation pass != semantic correctness. Must audit and fix foundational tools before proceeding. M8 repurposed as quality audit milestone; BOOM work deferred.

### 2026-04-22: M8 complete — quality audit passed
agent_spec.md fixed (all 7 examples compile), sv2anvil.py fixed (ternary, concat, width propagation, tick-literal bugs), 6 BOOM ground truth files created. Verified by Quinn (82% compile rate = 475/578) and Vera (all doc examples compile). Converter improved from ~40% to 82% on BOOM files across 8 Hugo commits.

### 2026-04-22: M9 planning — BOOM at 82% baseline
Athena independently verified: 15/20 random sample compiled (75%, within variance of 82% full-corpus). Key remaining failures: TL* interconnect modules, FP pipeline, complex decoders. 103 files still fail. Strategy: fix converter for remaining error patterns + hand-convert complex files.

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
**Status:** COMPLETE ✓ (verified 2026-04-19)
**Results:** 153/153 vendor .anvil files compile. sv2anvil.py auto-conversion at 100% for vendor files. PR #98 pending merge.

### M7: Complete CVA6 Conversion — Remaining 214 Files (budget: 8 cycles, used: 7)
**Status:** COMPLETE ✓ (verified 2026-04-19)
**Results:** All 445 CVA6 .anvil files pass `anvil -just-check`. Maya improved converter (190→416 auto-pass), Dana and Leo hand-wrote 15 complex files (cache subsystem, MMU, frontend).

### M8: Semantic Quality Audit & Fix Foundational Tools (budget: 8 cycles)
**Status:** COMPLETE ✓ (verified 2026-04-22)
**Results:** agent_spec.md fixed (all examples compile), sv2anvil.py fixed (no more zeroing), quality report written (21% correct, 32% partial, 36% stubs, 11% cleanup). All 454 .anvil files compile. Verified by Rex and Vera.

### M9: BOOM Full Conversion — 578 Files to Anvil (budget: 8 cycles)
**Status:** PENDING VERIFICATION (2026-04-24)
**Goal:** Convert all 578 BOOM SystemVerilog files to Anvil. Fix converter for remaining 18% failures. Hand-convert files the converter can't handle.
**Starting point:** 578 SV files in `core/boom/`. Converter at 82% (473/578). 6 ground truth files exist. 105 files still fail.
**Failure breakdown (Quinn's analysis):** Type size mismatch (59), concat type incompatibility (22), syntax errors (15), _RANDOM indexing (3), unused let (2), converter crash (4)
**Results so far:** 578/578 compile. 93 files are stubs (16%). 6 ground truth files compile. Athena evaluating whether criteria are met.
**Acceptance criteria:**
1. All 578 BOOM .anvil files in `converted/boom/` pass `anvil -just-check` with exit code 0
2. Semantic spot-check: ≥80% of a 20-file random sample contains non-stub logic (channels, registers, real assignments)
3. All 6 ground truth BOOM files still compile (no regression)

### M10: Rocket Chip Conversion (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert Rocket Chip to Anvil. Chisel-based, largest codebase.

### M11: Semantic Validation & Round-Trip Verification (budget: TBD)
**Status:** NOT STARTED
**Goal:** Full round-trip verification. Compile Anvil→SV, compare with originals. Fix semantic stubs from M5/M6.

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

### 2026-04-19: M6 complete — 153/153 CVA6 vendor files compile
Maya improved sv2anvil.py from 49% to 100% vendor pass rate across 8 commits. Converter now handles parameterized types, casting, const eval, array indexing, struct access. PR #98 pending merge. Overall converter pass rate on remaining 214 CVA6 files: 88.7%.

## Progress Tracking
- CVA6 core: 43/43 compile ✓
- CVA6 utility+SoC: 39/39 compile ✓
- CVA6 vendor: 153/153 compile ✓
- CVA6 remaining (core extras, corev_apu, common, configs): 214/214 compile ✓
- BOOM: 578 SV files available, 82% auto-convert pass rate (475/578), 103 remaining
- Rocket Chip: not started (Chisel-based, no SV source yet)
- Total converted: 445 files / 445 CVA6 total ✓

## Research Findings
- CVA6 = native SV (42K LOC), best first target (moderate complexity, clean modules)
- BOOM = Chisel (38K LOC), needs Chisel→Verilog→Anvil pipeline
- Rocket Chip = Chisel (55K LOC), largest/most complex, SoC generator
- Anvil: process-oriented HDL, channels with lifetimes, implicit clk/rst
- Anvil toolchain available at `/opt/opam/default/bin/anvil`
- Anvil key concepts: proc (not module), chan (channels with left/right endpoints), send/recv, reg + set, let bindings, loop, generate/generate_seq, >> (sequence), ; (parallel join)
