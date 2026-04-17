# Roadmap — BOOM/Rocket/CVA6 to Anvil Conversion

## Project Goal
Convert three RISC-V processor implementations (BOOM, Rocket Chip, CVA6) from their source HDL to Anvil, then verify equivalence by compiling Anvil back to SystemVerilog.

## ⚠ CRITICAL COURSE CORRECTION (2026-04-17)

**All 27 converted .anvil files fail to compile.** Zero files pass `anvil -just-check`. The converter produces fundamentally invalid Anvil syntax:
- Uses `right logic` / `left logic` (bare types after direction) — Anvil requires channel-typed endpoints
- Uses `(logic[N])` parenthesized types incorrectly
- Uses SV-style `ariane_pkg::` scoping — not valid Anvil
- Treats Anvil like SV with different keywords — but Anvil is channel-based with send/recv, not port-based

**Root causes:**
1. sv2anvil.py is regex-based (human feedback #61/#62) — needs proper parser
2. Workers and converter both lack understanding of actual Anvil semantics
3. "Verification" never actually ran the compiler — only compared logic structure

**All M1-M2.2 "complete" milestones are invalid.** The .anvil files exist but none compile. We are effectively starting over on the conversion quality front.

## Milestones

### M1: Research & Foundation (budget: 4 impl cycles)
**Status:** COMPLETE (but output quality invalidated — see course correction above)

### M1.1–M2.2: Previous conversion batches
**Status:** INVALIDATED — all 27 .anvil files fail to compile. Code exists but is syntactically wrong.

### M3: Anvil Compiler Validation & Reference Conversion (budget: 8 cycles) — CURRENT
**Status:** IN PROGRESS
**Goal:** Establish a correct Anvil conversion workflow by:
1. Writing 1-2 small CVA6 modules in valid Anvil BY HAND, verified against the actual compiler (`anvil -just-check`)
2. Understanding Anvil's channel-based communication model vs SV's port model
3. Documenting the correct SV→Anvil mapping patterns (ports→channels, always_comb→let, always_ff→reg+loop, etc.)
4. Rebuilding sv2anvil.py as a proper AST-based parser (not regex), targeting compilable output
5. All output MUST pass `anvil -just-check` — no exceptions

**Acceptance criteria:**
- At least 2 CVA6 modules compile with `anvil -just-check` with zero errors
- sv2anvil.py rewritten with proper SV parser (e.g., pyverilog or custom AST)
- A mapping guide doc exists showing correct SV→Anvil patterns
- The converter's output for alu.sv passes `anvil -just-check`

### M4: Re-convert CVA6 Core with Validated Toolchain (budget: TBD)
**Status:** NOT STARTED
**Goal:** Re-convert all 43 CVA6 core modules using the corrected converter and manual cleanup. Every file must pass `anvil -just-check`.

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

## Progress Tracking
- CVA6 top-level core: 0/43 with valid Anvil (27 files exist but none compile)
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
