# PPDE - Personalized Predictive Debugging Engine

A static analysis engine designed to learn *your* historical coding patterns and flag statistically unusual deviations.

> This repository focuses on system design, modeling discipline, and testable architecture - not feature completeness.

---

## Quick Start

```bash
# Clone and run (Python 3.10+, stdlib only)
git clone <this-repo>
cd ppde
python3 -m ppde.cli analyze .
```
## The Problem

Most static analysis tools fail in one of two ways:

1. High noise
They flag every possible “bad practice” without regard for context, leading developers to ignore warnings entirely.

2. Rigid heuristics
They encode fixed rules or style opinions that don’t reflect how you actually write code.

In practice, this means real issues are buried under irrelevant warnings or the tool is turned off altogether.

## What PPDE Is Trying to Do

PPDE takes a different approach:

Instead of enforcing universal rules, it measures how you typically write code and highlights deviations from your own historical norms.

Concretely:

- It analyzes Git history to learn how often certain patterns appear in specific contexts.
- It compares new code against that baseline.
- It flags patterns that are statistically unusual for you, not globally “bad”.

## Current MVP State

The architecture is complete and fully tested, but the historical frequency table is intentionally stubbed.

That means:
- All detectors run
- Context classification works
- Surprise scoring logic is implemented
- Warning gating and explanation logic are active

…but no warnings are produced yet because the system starts in cold-start mode with no historical baseline.

This is deliberate. When there isn’t enough data, PPDE stays silent rather than guessing.

## What Works Today

- 5 AST-based pattern detectors (pure, boolean functions)
- Context classification across 48 bounded buckets
- Deterministic frequency-based surprise scoring
- Stability-aware warning gating
- Explanation generation (data-first, neutral tone)
- End-to-end orchestration and CLI
- 131 tests covering all layers

## What’s Disabled (On Purpose)

- Historical frequency table construction
- Git history replay

The extension point is explicit and documented in orchestrator.py.

## Design Philosophy

### Dumb Detectors, Smart Aggregation

Detectors answer exactly one question: does this pattern exist here?

They don’t assign severity, confidence, or intent. All interpretation happens later, based on historical frequency and context.

### Conservative by Default

PPDE is biased toward silence:
- Patterns with insufficient historical data are suppressed
- New files are suppressed
- Volatile files require stronger evidence
- Output is capped (humans don’t read infinite warnings)

If the system isn’t confident, it does nothing.

### No Heuristics Disguised as Intelligence

There is:
- No machine learning
- No configuration DSL
- No severity scoring
- No autofix logic

These are intentional constraints. Frequency counting is deterministic, explainable, and testable and it matches the actual problem being solved.

## Architecture Overview
```powershell
Git History
    ↓
AST Pattern Detection
    ↓
Context Classification
    ↓
Frequency Model
    ↓
Surprise Scoring
    ↓
Warning Gating
    ↓
Explanation Generation
    ↓
CLI
```
## Detectors (Violation Patterns)

- has_timeout_parameter
- mutates_parameter
- writes_global_state
- has_broad_exception
- swallows_exception

Each detector is a small, pure function with a single responsibility.

## What’s Missing - and Why
### Historical Frequency Table

Building the table correctly requires replaying file contents at each commit, parsing historical ASTs, and recording pattern occurrences.

That work is straightforward but engineering-heavy, and it doesn’t add architectural insight. For this portfolio project, the emphasis is on design clarity, not shipping a half-tested implementation.

The system defaults to silence instead of guessing.

### File and Line Numbers

Warnings currently don’t include file paths or line numbers.

That information is presentation metadata, not part of the detection or modeling contract. It will be added once a presentation layer needs it.

## Example Output

Current behavior (cold start):
```yaml
Analyzed repository: /path/to/repo
Total findings: 0

No unusual patterns detected.
```

Expected behavior once a baseline exists:
```less
Finding #1
Detector: has_timeout_parameter

This call does not specify a timeout.
In similar contexts, this pattern appears 85% of the time (17 of 20).
This deviation is unusual for you.
```

## What This Is Not

- Not a linter
- Not a style checker
- Not a bug finder
- Not a replacement for code review

It’s a behavioral consistency engine.
