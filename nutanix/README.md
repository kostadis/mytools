# Nutanix v4 OpenAPI Audit

Local-only audit of Nutanix's v4 OpenAPI specifications. **Not an SDK.**

## Question this answers

What works and what doesn't in Nutanix's v4 OpenAPI specs? Where do they hold up under code generation, and where do they fall apart? Concretely: which defects is Nutanix's hand-written official SDK code papering over?

## Method

Every claim in the final report must trace back to a verifiable artifact: a validator rule violation, a code-generator error, or a diff hunk against an official SDK. No claims without artifacts.

## Pipeline

```
fetch_specs.sh   →  specs/vmm-v4.json
validate.sh      →  results/validation/vmm.txt
generate.sh      →  results/generation/vmm/{rust,typescript-fetch}/
diff_official.sh →  results/diffs/vmm.md
                 →  REPORT/{taxonomy,vmm,SUMMARY}.md
```

## Scope

**VMM namespace only** for the initial pass. Other v4 namespaces (networking, clustermgmt, iam, etc.) are out of scope until the harness proves itself on VMM.

## Reproducibility contract

Specs are not vendored. Run `tools/fetch_specs.sh` to land them locally. A fresh clone + `fetch_specs.sh` + `validate.sh` + `generate.sh` should reproduce the same findings.

## Layout

```
specs/                       # gitignored — populated by fetch_specs.sh
tools/
  fetch_specs.sh
  validate.sh
  generate.sh
  diff_official.sh
results/
  validation/<ns>.txt        # gitignored
  generation/<ns>/<lang>/    # gitignored
  diffs/<ns>.md              # gitignored
REPORT/                      # the only thing committed besides tools/
  taxonomy.md
  vmm.md
  SUMMARY.md
```
