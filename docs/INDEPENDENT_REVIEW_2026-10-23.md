# Independent review of the desktop milestone — 2026-10-23

An independent reviewer audited the Windows desktop workflow that was added
in commit `0957f1d` (the PySide6 GUI, the manual quality-control ledger and
the report refresh). The review was read-only: no repository file was
modified by the reviewer, and every finding was reproduced with an
executable probe before it was reported.

The milestone is **not** a production milestone. Two of the findings were
P1: the review panel took its authority from the operator's own text boxes,
and a running worker thread could be destroyed together with the window,
which aborts the interpreter (`0xC0000409`) instead of reporting a failure.

## Findings

| # | Sev | Area | Defect | Status |
|---|---|---|---|---|
| P1-1 | P1 | Authority | The review panel was fed from whatever the operator had typed into the approval text boxes, so a wider approval could be swapped in after the run | Fixed — `55eaef1` |
| P1-2 | P1 | Export | `apply_review_corrections` rewrote the export before it knew whether the correction was allowed | Fixed — `f1f0aed` |
| P1-3 | P1 | Threading | The worker `QThread` was parented to the window, so closing the window while a job ran destroyed a running thread and aborted the process | Fixed — `55eaef1` |
| P2-1 | P2 | Cancellation | A cancel was ignored for any job smaller than one batch: the run published anyway | Fixed — `957a1e0` |
| P2-2 | P2 | Privacy | The plaintext customer checkpoint shards stayed in the output folder after a successful run | Fixed — `957a1e0` |
| P2-3 | P2 | Consistency | `Manual_Review.csv` was not regenerated, so it contradicted the corrected export | Fixed — `f1f0aed` |
| P2-4 | P2 | Responsiveness | Reading a multi-million row export and applying the corrections ran on the GUI thread | Fixed — `55eaef1` |
| P2-5 | P2 | Audit trail | The ledger recorded neither the rules version nor the approval identity | Fixed — `55eaef1` |
| P2-6 | P2 | Injection | The operator's reason was written into the export without the formula sanitizer | Fixed — `f1f0aed` |
| P2-7 | P2 | Labelling | The corrected export took its data class from the summary file instead of the run manifest | Fixed — `f1f0aed` |
| P2-8 | P2 | Input | The header was always read as UTF-8, whatever the operator had selected | Fixed — `55eaef1` |
| P2-9 | P2 | Transparency | The panel truncated the review list without saying how many rows were hidden | Fixed — `55eaef1` |
| P2-10 | P2 | Robustness | `export_reviews` had no error handling, so a failed refresh was silent | Fixed — `55eaef1` |
| P3-1 | P3 | Validation | A decision could name a record number of zero or less | Fixed — `55eaef1` |
| P3-2 | P3 | Test quality | The "runs off the main thread" test asserted nothing about the thread the work actually ran on | Fixed — `55eaef1` |

## Detail and resolution

### P1-1 — the panel must follow the run, not the operator

Before the fix, `_load_approved_codes()` read the approval manifest path and
the approval key path straight from the two text boxes. The probe loaded a
restricted approval into the window, then replaced the text with a wider
approval and reloaded: the panel offered every code the wider approval
issued.

After the fix the panel is bound to the *run*. The run manifest records the
approval manifest path and its SHA-256, the digest is verified before the
manifest is used, and the operator's key is only used to check that exact
manifest's signature. Pointing the box at a different manifest afterwards
does not widen the panel, and a run without an approval asserts no code at
all. `tests/integration/test_gui_review_approval.py` pins both behaviours.

### P1-3 — a running worker is never destroyed with the window

Before the fix the thread was created as `QThread(self)`, so the window
owned it. `closeEvent` called `thread.quit()` and waited five seconds; the
worker was still inside the classification loop, so the window was destroyed
with a live thread and the interpreter aborted with `0xC0000409` instead of
reporting the failure.

After the fix the worker is a plain `QThread` subclass with no event loop,
so it ends when the work is done and there is nothing to quit. A close
request while a worker is still running is refused, the worker is asked to
stop and joined, and the interpreter shuts the remaining workers down at
exit. The regression test starts a slow worker, asks the window to close and
asserts that the close was refused.

### P2-1 and P2-2 — cancellation and the checkpoint

A cancel was only read at a committed batch boundary, so a job with fewer
rows than one batch ignored it and published the export anyway. The flag is
now polled on a record interval, at every batch boundary and once more
before the trailing batch is published; a cancelled run never writes a
manifest and stays resumable.

The checkpoint shards hold the raw customer addresses in plain text. They are
now removed once the exports are published, unless the operator asks to keep
them with `--keep-checkpoint`.

### P1-2, P2-3, P2-6 and P2-7 — the correction path

Every decision is now validated before a single byte of the export is
written, so a rejected correction leaves the published export exactly as it
was. `Manual_Review.csv` is regenerated from the corrected rows, the
reconciliation is asserted, the operator's reason is protected against
spreadsheet formula injection, and the data class comes from the run
manifest. The review artefacts are hashed into the manifest.

## Review gap

The reviewer covered the GUI milestone only. The benchmark tool, the pack
build tool and the documentation changes of this session have not been
reviewed by an independent reviewer, and the report above therefore does not
cover them.
