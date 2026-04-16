# Anvil HDL Compiler — Research Findings

## Summary

The Anvil compiler **exists and is open-source** (MIT license), but is experimental (v0.1.0) and must be built from source. There are no pre-compiled binaries or standard package manager distributions.

## What is Anvil?

Anvil is a **general-purpose, timing-safe hardware description language** created at the National University of Singapore (NUS). It compiles Anvil source code to synthesizable **SystemVerilog**.

Key properties:
- Process-oriented HDL with channels and lifetimes
- Exposes registers, wires, and clock cycles for low-level control
- Guarantees timing safety via a novel type system
- Designs can interoperate with existing SystemVerilog codebases
- Written in **OCaml** (97.1%), built with Dune

## Repository

- **GitHub:** https://github.com/kisp-nus/anvil (also https://github.com/jasonyu1996/anvil)
- 518 commits, 26 stars, 9 forks (as of April 2026)
- Organization: `kisp-nus` (not "kisp-lab" — that is a different group)

## Installation

**No pre-compiled binaries available.** Must build from source.

### Build Requirements
- OCaml 5.2.0
- Verilator 5.024 (for simulation)
- opam package manager

### Build Steps
```bash
git clone https://github.com/kisp-nus/anvil.git
cd anvil
opam install . --deps-only
eval $(opam env) && dune build
```

For global installation: `opam install .`

Invoke with: `dune exec anvil -- [OPTIONS] <anvil-source-file>`

## Package Manager Search Results

| Package Manager | Package Name | Related to HDL? |
|----------------|-------------|-----------------|
| pip (PyPI) | `anvil` v0.0.2 | No — Python scaffolding tool |
| npm | `anvil` v0.0.6 | No — interactive tools library |
| cargo (crates.io) | N/A | No anvil HDL crate found |
| opam | Source install only | Yes — `opam install .` from repo |

**Anvil HDL is not available in any standard package registry.**

## Documentation & Resources

- **Docs site:** https://docs.anvil.kisp-lab.org (live, HTTP 200)
- **Online playground:** https://anvil.capstone.kisp-lab.org/ (no installation needed)
- **VS Code extension:** Available (referenced in docs)
- **Community chat:** https://anvilhdl.zulipchat.com

## Academic Paper

**"Anvil: A General-Purpose Timing-Safe Hardware Description Language"**
- Authors: Jason Zhijingcheng Yu, Aditya Ranjan Jha, Umang Mathur, Trevor E. Carlson, Prateek Saxena
- Venue: ASPLOS 2026
- arXiv: https://arxiv.org/abs/2503.19447

## Implications for This Project

1. **Compiler exists and is usable** — the critical unknown from the roadmap is resolved.
2. **Build toolchain is non-trivial** — requires OCaml 5.2.0 and opam, which may need CI setup.
3. **Compiles to SystemVerilog** — confirms round-trip verification path (SV → Anvil → SV) is feasible.
4. **Experimental status (v0.1.0)** — expect rough edges, limited error messages, possible breaking changes.
5. **Online playground** available for quick prototyping before local setup.
6. **Interop with existing SV** — important for incremental conversion of CVA6 modules.

## Recommendation

Proceed with building Anvil from source using opam/OCaml. Set up a Dockerfile or CI job to automate the build environment. Use the playground for initial experimentation with small CVA6 modules.
