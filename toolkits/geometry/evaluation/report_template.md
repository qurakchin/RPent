# Geometry replay report

> **This is a synthetic analytic corpus, not a real-platform accuracy baseline.**
> Errors measure whether the back-projection, masking, fitting, and refusal
> contract stays consistent with ideal geometry. They do not measure sensor
> noise, grounding or segmentation model quality, or robot task success.

## Provenance

| field | value |
| --- | --- |
| corpus version | `{{CORPUS_VERSION}}` |
| corpus fingerprint | `{{CORPUS_FINGERPRINT}}` |
| cases replayed | {{CASE_COUNT}} of {{CORPUS_CASES}} |
| excluded | {{EXCLUDED_CASES}} — {{EXCLUSION_REASON}} |
| mask source | `{{MASK_SOURCE}}` |
| git revision | `{{GIT_REVISION}}` |
| generated | `{{GENERATED_AT}}` |
| quality config | `{{QUALITY}}` |

Replay recomputes every RGB-D frame, camera pose, pixel, and mask from the
manifest parameters. The reference is the exact unnoised visible surface; it is
computed before the tool runs and shares no fitting code with the tool.

## Coverage

{{STATUS_TABLE}}

Center error ({{CENTER_ERROR}}) and extent error ({{EXTENT_ERROR}}) use
mean / median / p95 / max over cases that returned a measurement. Extent is the
world-frame axis-aligned range of the visible surface, not the box's true
dimensions.

Visible cases refused: {{VISIBLE_REFUSED}}. Rejected cases answered:
{{UNEXPECTED_ACCEPT}}.

## Per group

{{GROUP_TABLE}}

## Quality warnings

{{WARNING_TABLE}}

## Cases for review

{{BAD_CASES}}

## How to import a real-platform corpus

Add an adapter that emits the same case shape: RGB-D, intrinsics,
`world_from_camera` with its convention, the chosen `[row,col]`, its frozen
mask, and an independently measured reference. Keep real-sensor runs in their
own report with their platform, sensor, and calibration revision; do not mix
them into this synthetic report or treat their numbers as interchangeable.
