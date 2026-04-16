# Roadmap — BOOM/Rocket/CVA6 to Anvil Conversion

## Project Goal
Convert three RISC-V processor implementations (BOOM, Rocket Chip, CVA6) from their source HDL to Anvil, then verify equivalence by compiling Anvil back to SystemVerilog.

## Milestones

### M1: Research & Foundation (budget: 4 impl cycles)
**Status:** COMPLETE (verified with caveats)
**Goal:** Deeply understand Anvil language, the three target repos, and create the initial sv2anvil.py converter and worker skill files.
- [x] Research Anvil language: syntax, semantics, compilation, timing model (Iris report)
- [x] Analyze BOOM, Rocket Chip, CVA6 repo structures (Orion report)
- [x] Create initial sv2anvil.py converter (Maya, PR #2)
- [x] Create agent_spec.md, worker_skill.md, timing_handling.md (Kai, PR #3)
- [x] Convert CVA6 ALU as proof-of-concept (Nora, PR #4 — manual, ~85% complete)
- [x] Clone CVA6 repo and research Anvil compiler (Leo, PR #1)

**Verification findings (Apollo/Vera):**
- sv2anvil.py had 3 critical bugs: ternary/bit-slice collision, flattened always_comb, multi-line if parsing
- Manual alu.anvil was excellent quality
- Compiler research was thorough

### M1.1: sv2anvil.py Bug Fixes (budget: 4 fix cycles — DEADLINE MISSED)
**Status:** WORK COMPLETE, PR #5 NOT MERGED
**Goal:** Fix 3 critical bugs found during verification.
- [x] Bug 1: Ternary vs bit-slice colon collision — fixed via _mask_brackets()
- [x] Bug 2: Flattened always_comb — rewritten to be structure-aware
- [x] Bug 3: Multi-line if parsing — added balanced paren matcher
- [x] Bug 4 (follow-up): Case arm ternary garbling — split assignment before convert_expr
- [x] Bug 5 (follow-up): Default binding ordering — moved before match/if blocks
- [ ] PR #5 merge pending

**Known remaining issues (from Vera's report, not addressed):**
- SV `inside` operator not converted (minor)
- SV replication `{N{expr}}` mangled (minor)
- Combinational signals declared as `reg` instead of `let` (moderate)

### M2: CVA6 Core Conversion (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert CVA6 core modules to Anvil using improved sv2anvil.py + manual conversion.
- CVA6 is pure SystemVerilog (~42K LOC), best first target
- Use both automated and manual approaches in parallel
- Iterate on converter based on results from each module

### M3: BOOM Conversion (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert BOOM to Anvil. Chisel-based, needs Chisel→SV→Anvil pipeline.

### M4: Rocket Chip Conversion (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert Rocket Chip to Anvil. Chisel-based, largest codebase.

### M5: Validation & Polish (budget: TBD)
**Status:** NOT STARTED
**Goal:** Full round-trip verification. Compile Anvil→SV, compare with originals.

## Lessons Learned
- **Planning budget:** 3 Athena cycles for M1 planning was too many. Target 1 cycle for future milestones.
- **Verification catches real bugs:** Apollo/Vera found 3 critical sv2anvil.py bugs that Ares's team missed. Verification is essential.
- **Manual conversion >> auto conversion (for now):** Nora's manual alu.anvil was far better than sv2anvil.py output. Manual conversion workers are critical path.
- **Fix rounds need focused scope:** M1.1 used 4 cycles for what was 2 cycles of actual work because the fix PR wasn't merged. Need to ensure PRs get merged within the cycle budget.
- **sv2anvil.py is a scaffold, not the primary tool:** The converter handles simple patterns but breaks on real-world SV. Strategy should be: auto-convert for scaffolding, manual cleanup for correctness.
- **Break milestones smaller:** M1 was scoped correctly. Future milestones should be similarly focused (3-5 modules per milestone, not entire repos).

## Research Findings
- CVA6 = native SV (42K LOC), best first target (moderate complexity, clean modules)
- BOOM = Chisel (38K LOC), needs Chisel→Verilog→Anvil pipeline
- Rocket Chip = Chisel (55K LOC), largest/most complex, SoC generator
- Anvil: process-oriented HDL, channels with lifetimes, implicit clk/rst
- Anvil toolchain v0.1.0 — build from source (OCaml 5.2.0, opam, dune)
