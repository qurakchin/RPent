# Geometry evaluation

`geometry` is a shared tool, so it ships with its own evaluation. This package
replays a frozen synthetic-analytic corpus on CPU and writes a manifest, raw
results, and a report.

```bash
python -m toolkits.geometry.evaluation.experiment --output-dir /tmp/geometry-eval
python -m toolkits.geometry.evaluation.experiment --output-dir /tmp/geometry-eval --fallback-mask
```

The corpus is a deterministic pure function of stored scene parameters:
80 cases (56 clean, 12 high depth noise, 12 refusal cases) rendered from box and
table geometry. The reference is the exact unnoised visible surface, computed
independently of the tool. Replay loads frozen masks so grounding and
segmentation models are not part of the measurement; `--fallback-mask`
exercises the built-in depth-region segmenter instead. Fallback runs replay only
the 68 visible cases: refusal requires an empty mask, which the model-free
segmenter cannot infer from a scene with no target. A fallback mask that leaks
into a table of similar color is reported as a partial fit, not hidden.

The evaluation uses only the core `numpy` and RPent dependencies, so no extra
is required. Its output is evidence of pipeline consistency, not a real-sensor
accuracy baseline; import real-platform cases through the adapter described in
the report template and keep their reports separate.
