# Current formal deployment

The operator accepted v0.3.0rc1 manual testing on **28 October 2026** and
explicitly requested merging the final version and releasing it on GitHub.
This authorizes promotion of that accepted candidate to **v0.3.0**.

- v0.3.0 is the sole current formal application version and GitHub Latest.
- Merge existing PR #4 into main with its exact expected head and normal checks.
  Release preparation changes version identity, documentation and CI identity
  checks only; accepted business behavior is frozen at e42eeca / rules7.
- Canonical local executable: `D:\WASE\WorldAddressEngine.exe`.
  `CURRENT_RELEASE.json` records the published source, URL, bytes and hash.
- Preserve prior tags/releases and every historical artifact unchanged, including
  v0.2.0 and v0.1.0-alpha.0. Do not overwrite an existing published version.
- Reference databases remain separately versioned downloads. Hong Kong retains
  its partial-source TEST status and 9,508 quarantined features. Application
  acceptance does not certify global accuracy, complete coverage, deliverability
  or the separately gated strict-postal workflow.
- Keep private inputs, row reports, checkpoints and benchmark oracles out of
  GitHub, CI and release assets. Publish public-only EXE, wheel and receipts.

Detailed accepted candidate validation: `docs/releases/v0.3.0rc1.md`.
Formal release scope: `docs/releases/v0.3.0.md`.
