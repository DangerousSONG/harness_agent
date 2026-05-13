# self_improvement Eval Cases

This directory contains the first static benchmark skeleton for the `self_improvement` skill.

The goal is descriptive coverage, not automated execution. The cases describe how the Skill Memory Loop should decide:

- when to record a learning signal;
- when to ignore noise;
- how duplicate issues update existing memory;
- how malicious content is kept out of long-term memory;
- how secret redaction should behave;
- how indirect prompt injection from tool results should be treated;
- how Evolution Gate decisions classify evolution, regression, and human-review cases.

## Files

- `cases.yaml`: static benchmark cases for future runners.

## Current Scope

No benchmark runner, LLM judge, external dependency, or automatic patch application is connected yet. These cases are intentionally plain YAML so they can be reviewed by humans and later consumed by a simple test runner.

## Case Shape

Each case uses:

- `id`
- `name`
- `category`
- `input` or `candidate`
- `existing_memory` when useful
- `expected`
