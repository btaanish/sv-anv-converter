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

### M2.1: CVA6 Core Batch 2 — Small Modules (budget: 6 cycles, used: 4)
**Status:** COMPLETE (verified via PRs #15-#23)
**Goal:** Convert the next 8 small CVA6 core modules (under 150 lines each).
- [x] cva6_accel_first_pass_decoder_stub.sv (PR #15)
- [x] cvxif_compressed_if_driver.sv (PR #16)
- [x] cvxif_issue_register_commit_if_driver.sv (PR #17)
- [x] alu_wrapper.sv (PR #18)
- [x] raw_checker.sv (PR #19, fix PR #23)
- [x] cvxif_fu.sv (PR #20)
- [x] amo_buffer.sv (PR #21)
- [x] ariane_regfile_fpga.sv (PR #22)

**Converted so far: 14/43 top-level core modules (33%)**

### M2.2: CVA6 Core Batch 3 — Medium-Small Modules (budget: 6 cycles)
**Status:** NEXT
**Goal:** Convert 6 medium-small CVA6 modules (133-234 lines).
Target modules:
- zcmt_decoder.sv (133 lines)
- cva6_rvfi_probes.sv (145 lines)
- lsu_bypass.sv (145 lines)
- perf_counters.sv (217 lines)
- cva6_fifo_v3.sv (231 lines)
- aes.sv (234 lines)

### M2.3: CVA6 Core Batch 4 — Medium-Large Modules (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert 7 medium-large CVA6 modules (277-365 lines).
Target: controller, serdiv, axi_shim, issue_stage, store_buffer, scoreboard, instr_realign

### M2.4: CVA6 Core Batch 5 — Large Modules (budget: TBD)
**Status:** NOT STARTED
**Goal:** Convert large CVA6 modules (400+ lines).
Target: store_unit, commit_stage, acc_dispatcher, id_stage, trigger_module, fpu_wrap, load_unit, cva6_rvfi, ex_stage, macro_decoder, load_store_unit, compressed_decoder, issue_read_operands, cva6.sv, decoder, csr_regfile

### M2.5: CVA6 Subdirectories (budget: TBD)
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
- **M2.1 completed efficiently in ~4 cycles:** 8 small modules, 1 bug found in verification (raw_checker generate vs generate_seq). Pattern works well.
- **generate vs generate_seq matters:** Parallel generate produces a vector; generate_seq does accumulation. Workers need to recognize SV always_comb scan loops as needing generate_seq.

## Progress Tracking
- CVA6 top-level core: 14/43 converted (33%)
- CVA6 subdirectories: 0/~71 converted (0%)
- BOOM: not started
- Rocket Chip: not started

## Research Findings
- CVA6 = native SV (42K LOC), best first target (moderate complexity, clean modules)
- BOOM = Chisel (38K LOC), needs Chisel→Verilog→Anvil pipeline
- Rocket Chip = Chisel (55K LOC), largest/most complex, SoC generator
- Anvil: process-oriented HDL, channels with lifetimes, implicit clk/rst
- Anvil toolchain v0.1.0 — build from source (OCaml 5.2.0, opam, dune)
