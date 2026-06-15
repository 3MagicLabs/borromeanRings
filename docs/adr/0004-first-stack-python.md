# ADR-0004 — First governed stack = Python

**Status:** Accepted

## Context
borromeo's first governed project is its own repo. We need one concrete language toolchain to wire
real checks against, chosen for mature, fast, widely-installed deterministic tooling.

## Decision
**Python** is the first stack. `verify.sh` targets: `ruff format` (format) + `ruff check` (lint) +
`mypy` (types) + `pytest` (+ coverage, reported as a ratchet per QAS-7) + `bandit` (security).

## Alternatives considered
- **TypeScript/Node** — viable, strong tooling; rejected for v0 only because Python's check tools
  are lighter to install on WSL2 and the Maintainer's first target is Python.
- **Go** — excellent built-in tooling; deferred — not the first target stack.
- **Multi-language from day one** — rejected: violates "no premature building"; the uniform check
  contract (ADR-0005) lets other stacks be added later without re-architecting.

## Consequences
- (+) Mature, fast, deterministic tools that map cleanly onto one check each (high cohesion).
- (+) `bandit`-only security in v0 keeps install light; `semgrep` is a future check (DD-2).
- (−) Other stacks aren't governed yet — by design; each becomes a new set of checks behind the
  same contract.
