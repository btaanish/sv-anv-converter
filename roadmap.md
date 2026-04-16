# Roadmap — BOOM/Rocket/CVA6 to Anvil Conversion

## Project Goal
Convert three RISC-V processor implementations (BOOM, Rocket Chip, CVA6) from their source HDL to Anvil, then verify equivalence by compiling Anvil back to SystemVerilog.

## Milestones

### M1: Research & Foundation (cycles: 4)
**Status:** IN PROGRESS → handing to Ares for implementation (research done, 3 cycles used by Athena)
**Goal:** Deeply understand Anvil language, the three target repos, and create the initial sv2anvil.py converter and worker skill files.
- [x] Research Anvil language: syntax, semantics, compilation, timing model (Iris report complete)
- [x] Analyze BOOM repo structure and complexity (Orion report complete)
- [x] Analyze Rocket Chip repo structure and complexity (Orion report complete)
- [x] Analyze CVA6 repo structure and complexity (Orion report complete)
- [ ] Create initial sv2anvil.py converter
- [ ] Create agent_spec.md and worker_skill.md for manual conversion workers
- [x] Identify key conversion challenges (especially timing)
- [ ] Begin timing_handling.md
- [ ] Convert one small CVA6 module as proof-of-concept

**Research findings:**
- CVA6 = native SV (42K LOC), best first target (moderate complexity, clean modules)
- BOOM = Chisel (38K LOC), needs Chisel→Verilog→Anvil pipeline
- Rocket Chip = Chisel (55K LOC), largest/most complex, SoC generator
- Anvil: process-oriented HDL, channels with lifetimes, implicit clk/rst
- Anvil toolchain v0.1.0 — compiler availability/installation unknown (critical gap)

### M2: CVA6 Conversion (cycles: 10)
**Status:** NOT STARTED
**Goal:** Convert CVA6 (SystemVerilog-native, likely simplest) to Anvil. Validate via round-trip compilation.
- CVA6 is pure SystemVerilog, making it the best first target for sv2anvil.py
- Use both automated (sv2anvil.py) and manual (worker-driven) approaches in parallel
- Iterate on converter and skill files based on results

### M3: BOOM Conversion (cycles: 12)
**Status:** NOT STARTED
**Goal:** Convert BOOM to Anvil. BOOM is Chisel-based, so may need Chisel→SV→Anvil pipeline.

### M4: Rocket Chip Conversion (cycles: 12)
**Status:** NOT STARTED
**Goal:** Convert Rocket Chip to Anvil. Similar Chisel challenge as BOOM but larger codebase.

### M5: Validation & Polish (cycles: 6)
**Status:** NOT STARTED
**Goal:** Full round-trip verification of all three conversions. Ensure compiled SV matches original implementations.

## Lessons Learned
- Cycle 1-2: Research phase took 2 cycles (Athena + 2 workers). Workers delivered comprehensive reports.
- Cycle 3: Athena defined M1 deliverables and created issue #3 for Ares. Total planning: 3 cycles.
- Critical unknown: Anvil compiler availability — must be resolved early in M1 implementation.
- Budget note: 3 Athena cycles used for planning M1. Future milestones should aim for 1-2 planning cycles.

## Notes
- BOOM and Rocket Chip are written in Chisel (Scala-based HDL), not SystemVerilog directly. They can emit Verilog. This may require a Chisel→Verilog→Anvil pipeline.
- CVA6 is SystemVerilog-native, making it the natural first conversion target.
- The spec mentions sv2anvil.py, agent_spec.md, and worker_skill.md as "given in the workspace" but they don't exist yet — we need to create them.
