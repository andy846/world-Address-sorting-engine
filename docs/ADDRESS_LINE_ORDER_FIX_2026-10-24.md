# Address Line Order Regression Fix - 2026-10-24

## Confirmed cause

The reported 9,604-record run produced 4,867 determined, 2,484 inferred and
2,253 unresolved, versus the previous 7,136 / 2,351 / 117 baseline. Input,
reference SQLite, catalogue and classifier rules fingerprints were identical.

The new run recorded selected columns in order NAME_ADDRESS_LINE2, LINE3,
LINE4, LINE5, LINE1. Qt QListWidget.selectedItems() reflects selection order,
not necessarily the source/display order. Deselecting/reselecting the first
line can therefore move it to the end even though the displayed column list
has not moved. Address-role inference legitimately depends on recipient,
street, locality and trailing country placement, so this silently changed the
input being classified. It is a GUI mapping bug, not operator error.

A local count-only control replay using that exact wrong mapping reproduced
all reported status counts and every code, status, reason and candidate list:
**zero row-level differences** from the reported result. No classifier-rule
changes since the previous baseline were found. The original baseline used
automatic NAME_ADDRESS_LINE1 through LINE5 ordering.

## Fix and regression protection

The GUI now enumerates selected entries by their displayed/source positions,
never selectedItems() ordering. This also preserves arbitrary/custom header
order rather than sorting labels alphabetically or numerically. Preview and
new analysis consume the same ordered mapping. Selection guidance explains
this invariant. CLI explicit ordering and pinned resume configurations are
not silently rewritten: a previously wrong-order job needs a new analysis in
a new empty output directory.

- Five new synthetic GUI regressions observed RED, then all 34 GUI cases GREEN.
- The frozen executable self-test now deliberately selects line 2, line 3,
  then line 1, and must attest `address_line_order_preserved: true`.
- The new self-test gate observed RED before implementation; combined GUI and
  packaging tests: 100 passed, 1 skipped.

## Actual local replay

The fixed GUI was exercised using the original private input and the same real
Extended k2 pack, selecting lines 2, 3, 4, 5 then 1 (the failing click sequence).
The transmitted mapping was nevertheless canonical lines 1 through 5.

| Status | Reported wrong order | Corrected source order |
| --- | ---: | ---: |
| Determined | 4,867 | 7,136 |
| Inferred | 2,484 | 2,351 |
| Unresolved | 2,253 | 117 |

All three corrected report CSVs (classified originals/codes, diagnostics and
country summary) are **byte-identical** to the previous successful rules.3
baseline, not merely equal in aggregate counts. Code coverage is restored to
98.78%; that is not a labelled-accuracy claim. Source fingerprint is unchanged;
the old successful and reported output checksums still verify. Checkpoint and
finalization state were removed after successful completion.

The corrected source-GUI job took 185.727 seconds with peak process RSS
87,924,736 bytes **while full real-pack regression and EXE packaging ran
concurrently**; do not compare this timing to an idle operator run or claim it
as a throughput baseline. Wrong-order classification-only control took 43.279
seconds and reproduced every reported inference field.

Corrected local output (never uploaded):
`D:\WASE\exports\AAAAA-country-analysis-line-order-fixed-20261024`.
Both real SQLite packs are unchanged: Compact 142,577,664 bytes; Extended
1,087,344,640 bytes. No rule or database rebuild was needed.

## Final validation

- Implementation commit: `79abee7`.
- Full real-k2/slow-check regression: **1,045 passed, 1 skipped, 2 pre-existing
  strict-retrieval xfailed in 326.00 seconds**; command exit 0.
- Independent review: no actionable findings. The reviewer separately ran
  100 GUI/packaging cases (1 skip), 33 runner cases, CSV/XLSX/custom-header and
  resume compatibility probes, and verified old click-order code fails the
  strengthened self-test. No private inputs were accessed by the reviewer.
- Frozen Windows build and actual self-test passed, including
  `address_line_order_preserved: true`, offline normalization, case summaries,
  icon loading and legacy approval refusal.
- Separately named local EXE opened for operator testing:
  `D:\WASE\out\WorldAddressEngine-line-order-fix-20261024.exe`.
- EXE size: **48,708,246 bytes**; SHA-256
  `b915c75b7112798d7fd08776ea6bb6083fcda34dc69b770d9dfbfabd42d6eda0`.

The initial regression suite did not exercise deselect/reselect ordering.
The new tests deliberately cover that previously missed interaction instead of
reducing country inference safeguards to conceal the symptom.

## Privacy and remaining gates

The original customer CSV, prior successful run and reported run are read only.
Any corrected private output is in a separate ignored exports directory. No
customer addresses, row-level comparisons, checkpoints or outputs are uploaded
or used in public regression fixtures. Only aggregate receipts are published.
The classifier, country catalogue and real k2 databases remain unchanged.

Reproducing the prior result proves this input-order regression is fixed, not
that all inferred country codes are ground-truth accurate. Existing labelled
accuracy, high-volume and operator acceptance gates remain applicable. No
published release overwrite or main merge is part of this fix.
