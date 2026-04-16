# Roadmap — BOOM/Rocket/CVA6 to Anvil Conversion

## Project Goal
Convert three RISC-V processor implementations (BOOM, Rocket Chip, CVA6) from their source HDL to Anvil, then verify equivalence by compiling Anvil back to SystemVerilog.

## Milestones

### M1: Research & Foundation (budget: 4 impl cycles)
**Status:** COMPLETE
**Goal:** Deeply understand Anvil language, the three target repos, and create the initial sv2anvil.py converter and worker skill files.
- [x] Research Anvil language: syntax, semantics, compilation, timing model
- [x] Analyze BOOM, Rocket Chip, CVA6 repo structures
- [x] Create initial sv2anvil.py converter (PR #2)
- [x] Create agent_spec.md, worker_skill.md, timing_handling.md (PR #3)
- [x] Convert CVA6 ALU as proof-of-concept (PR #4)
- [x] Clone CVA6 repo and research Anvil compiler (PR #1)

### M1.1: sv2anvil.py Bug Fixes (budget: 4 fix cycles)
**Status:** COMPLETE
**Goal:** Fix critical bugs found during verification.
- [x] 5 bugs fixed (ternary/bit-slice, flattened always_comb, multi-line if, case arm ternary, default binding)
- [x] PR #5 merged

### M1.2: Merge Fixes + Convert First 5 CVA6 Modules (budget: 4 cycles)
**Status:** COMPLETE (verified, fixes merged via PRs #6-14)
**Goal:** Fix remaining sv2anvil.py gaps and convert 5 CVA6 modules.
- [x] sv2anvil.py v2: inside operator, replication, let vs reg (PR #6)
- [x] branch_unit.anvil (PR #7)
- [x] csr_buffer.anvil (PR #8)
- [x] ariane_regfile_ff.anvil (PR #9)
- [x] multiplier.anvil (PR #10)
- [x] mult.anvil (PR #11)
- [x] Verification fixes: regfile, multiplier, mult (PRs #12-14)

**Converted so far: 6/43 top-level core modules** (alu, ariane_regfile_ff, branch_unit, csr_buffer, mult, multiplier)

### M2.1: CVA6 Core Batch 2 — Small Modules (budget: 6 cycles)
**Status:** NEXT
**Goal:** Convert the next 8 small CVA6 core modules (under 150 lines each).
Target modules:
- cva6_accel_first_pass_decoder_stub.sv (34 lines)
- cvxif_compressed_if_driver.sv (66 lines)
- cvxif_issue_register_commit_if_driver.sv (66 lines)
- alu_wrapper.sv (71 lines)
- raw_checker.sv (73 lines)
- cvxif_fu.sv (79 lines)
- amo_buffer.sv (83 lines)
- ariane_regfile_fpga.sv (150 lines)

### M2.2: CVA6 Core Batch 3 — Medium Modules (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert medium-sized CVA6 modules (150-350 lines).
Target: zcmt_decoder, cva6_rvfi_probes, lsu_bypass, perf_counters, cva6_fifo_v3, aes, controller, serdiv, axi_shim, issue_stage, store_buffer, scoreboard, instr_realign

### M2.3: CVA6 Core Batch 4 — Large Modules (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert large CVA6 modules (350+ lines).
Target: store_unit, commit_stage, acc_dispatcher, id_stage, trigger_module, fpu_wrap, load_unit, cva6_rvfi, ex_stage, macro_decoder, load_store_unit, compressed_decoder, issue_read_operands, cva6.sv, decoder, csr_regfile

### M2.4: CVA6 Subdirectories (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert frontend/, cache_subsystem/, cva6_mmu/, pmp/, cvxif_example/, include/ packages.

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
- **Manual conversion >> auto conversion (for now):** Manual alu.anvil was far better than sv2anvil.py output. Strategy: auto-convert for scaffolding, manual cleanup for correctness.
- **Fix rounds need focused scope:** M1.1 used 4 cycles for what was 2 cycles of actual work because PR wasn't merged. Ensure PRs get merged within cycle budget.
- **1 module per worker per cycle:** M1.2 succeeded by assigning exactly 1 module per worker. Continue this pattern.
- **Parallel conversion + sequential verification works well:** Convert in parallel, verify fixes sequentially.
- **Scale workers for throughput:** With 8 modules to convert, hire 8 workers (1 each) rather than overloading fewer workers.

## Progress Tracking
- CVA6 top-level core: 6/43 converted (14%)
- CVA6 subdirectories: 0/~71 converted (0%)
- BOOM: not started
- Rocket Chip: not started

## Research Findings
- CVA6 = native SV (42K LOC), best first target (moderate complexity, clean modules)
- BOOM = Chisel (38K LOC), needs Chisel→Verilog→Anvil pipeline
- Rocket Chip = Chisel (55K LOC), largest/most complex, SoC generator
- Anvil: process-oriented HDL, channels with lifetimes, implicit clk/rst
- Anvil toolchain v0.1.0 — build from source (OCaml 5.2.0, opam, dune)
