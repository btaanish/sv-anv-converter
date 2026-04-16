# Roadmap — BOOM/Rocket/CVA6 to Anvil Conversion

## Project Goal
Convert three RISC-V processor implementations (BOOM, Rocket Chip, CVA6) from their source HDL to Anvil, then verify equivalence by compiling Anvil back to SystemVerilog.

## Milestones

### M1: Research & Foundation (cycles: 4)
**Status:** IN PROGRESS
**Goal:** Deeply understand Anvil language, the three target repos, and create the initial sv2anvil.py converter and worker skill files.
- [ ] Research Anvil language: syntax, semantics, compilation, timing model
- [ ] Analyze BOOM repo structure and complexity
- [ ] Analyze Rocket Chip repo structure and complexity
- [ ] Analyze CVA6 repo structure and complexity
- [ ] Create initial sv2anvil.py converter
- [ ] Create agent_spec.md and worker_skill.md for manual conversion workers
- [ ] Identify key conversion challenges (especially timing)
- [ ] Begin timing_handling.md

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
_(updated as project progresses)_

## Notes
- BOOM and Rocket Chip are written in Chisel (Scala-based HDL), not SystemVerilog directly. They can emit Verilog. This may require a Chisel→Verilog→Anvil pipeline.
- CVA6 is SystemVerilog-native, making it the natural first conversion target.
- The spec mentions sv2anvil.py, agent_spec.md, and worker_skill.md as "given in the workspace" but they don't exist yet — we need to create them.
