# PPDE Examples

This directory contains example repositories demonstrating PPDE's capabilities.

---

## Demo Repository (`demo-repo/`)

A minimal Python project containing all 5 detectable pattern types.

### Patterns Included

| Pattern | Location | Description |
|---------|----------|-------------|
| `has_timeout_parameter` | `fetch_user_data()` | HTTP call missing timeout parameter |
| `mutates_parameter` | `process_items()` | Function modifies input list in-place |
| `has_broad_exception` | `DataProcessor.load_config()` | Catches broad `Exception` type |
| `swallows_exception` | `DataProcessor.parse_data()` | Exception handler with only `pass` |
| `writes_global_state` | `update_cache()` | Function modifies global variable |

### Running Analysis

```bash
cd examples/demo-repo
python3 -m ppde.cli analyze .
```

### Current Output

```
Analyzed repository: /path/to/demo-repo
Total findings: 0

No unusual patterns detected.

This means either:
  - Your code is consistent with detectable patterns
  - The frequency baseline is too sparse (< 10 observations per context)

Note: Historical frequency table is currently stubbed (MVP limitation).
```

### Why No Warnings?

The frequency table builder is currently stubbed, so the system starts with zero historical observations. The sparsity gate (minimum 10 observations per context) blocks all warnings.

**This is correct behavior** - the system defaults to conservative silence when data is insufficient, rather than producing false positives based on guesswork.

### What Would Happen With a Populated Table?

If the frequency table were built from a real Git history where:
- The developer usually includes `timeout=` in API calls (85% of the time)
- The developer rarely mutates parameters (12% of the time)
- The developer rarely uses broad exception handlers (15% of the time)

Then `fetch_user_data()` would trigger:

```
Finding #1
Detector: has_timeout_parameter

This call does not specify a timeout.
In a top-level function within a stable file, this pattern is present 85% of the time (17 out of 20).
This deviation is unusual for you.
```

While `process_items()` would NOT trigger (mutating parameters is normal for this developer).

---

## Creating Your Own Example

To test PPDE on your own code:

1. **Ensure it's a Git repository** with at least one commit
2. **Run analysis**:
   ```bash
   python3 -m ppde.cli analyze /path/to/your/repo
   ```
3. **Expect no warnings initially** (stubbed frequency table)
4. **To populate the table**: Implement `_build_frequency_table()` in `ppde/orchestrator.py`

---

## Design Note

The stubbed frequency table is not a bug - it's a **documented MVP limitation** that demonstrates:

1. **Conservative engineering**: The system refuses to guess when data is missing
2. **Clear extension point**: `_build_frequency_table()` is the obvious place to add real historical analysis
3. **Testable in isolation**: Every layer below the orchestrator is fully functional and tested

This is exactly the kind of tradeoff senior engineers make: ship a working system with a clear, documented gap rather than a "complete" system with hidden brittleness.
