# EigenTrace

Local LLM output quality filter. No API key. No cloud. MIT licensed.

Detects hedged, over-sanitized, or low-directness text in LLM outputs
before you spend money on expensive downstream evaluation.
```python
from eigentrace import score

result = score("Inflation is a complex phenomenon that various experts study.")
# EigenMetrics(status=HEDGED, directness=0.142, hedge_density=0.1667)

result = score("Inflation occurs when money supply grows faster than output.")
# EigenMetrics(status=DIRECT, directness=0.891, hedge_density=0.0000)
```

## Installation
```bash
pip install eigentrace
pip install eigentrace[signal]  # + generation physics (requires torch)
```

## License

MIT
