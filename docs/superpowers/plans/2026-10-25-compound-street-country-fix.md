# Compound numbered-street geographic evidence correction

User requested fixing the two publicly documented TD/MY misclassifications.
Continue the existing isolated feature branch and Draft PR #3; preserve main,
v0.1.0 Latest, all published data/release assets and old rules6 checkpoints.
The user already authorized autonomous fixes, TDD and independent reviews.

Root cause reproduced against both real k2 packs: Lai (TD, GeoNames 2429296)
inside `288 LAI CHI KOK ROAD`, and Yan (MY ADM2, 1735487) inside
`2A YAN HING STREET`. Only immediate street suffixes were excluded; the
multiword prefix leaked into geographic candidate evidence.

Design: reject geographic occurrences wholly inside a bounded Latin numbered
street span on the same line. Preserve identical terms occurring independently
elsewhere, comma/line boundaries, explicit countries/hints, substantial city
destinations and existing conflict guards. Do not let the regional pack override
assigned results. After removing false global evidence, the two cases become
eligible unresolved results and the verified optional ALS pair resolves HK.
No address-specific whitelist, blacklist or database edits. Global packs and
regional snapshot remain byte-identical. Increment country rules for new runs.

- [x] RED synthetic compound-street, independent-city and real-pack regressions.
- [x] GREEN minimal role filter; independent bounded review and negatives.
- [x] Full regression; unchanged frozen public bank all labels pass; private
  enabled/disabled replay and quantify every code/status change locally.
- [x] Commit/push existing Draft PR, remote CI and rebuilt Windows EXE smoke.

No new formal release or merge is requested by this bugfix. A full million-row
performance rerun is needed only if a measured performance concern arises;
focused boundedness checks and existing cache/job/recovery tests apply first.

Initial RED: 16 failed / 32 passed across synthetic and both actual global packs.
First related suite: 245 passed. Added long-number guard RED (eight-digit house
number must not revive a street homonym); numeric matching is linear within the
existing 10,000-character input cap rather than an arbitrary seven-digit limit.

Independent review found punctuated multiword aliases lost by fragment-only
occurrence matching: Washington, D.C. and New, Delhi (two RED regressions).
Fix: recognize/mask numbered streets within comma/semicolon fragments first,
then normalize the complete line as before. A non-alias boundary marker prevents
joining words across a removed street into a fabricated city. Explicit country
and conflict paths are unchanged. Country rules advance to country.7; previous
rules6 workspaces/oracles remain preserved and must not be relabelled.

Completed runtime a99d94e, rules7. Final focused tests: 226 passed in 11.93s.
Full local suite: 1,738 passed / 1 skipped / 2 pre-existing xfails in 358.66s.
Both exact-runtime CI runs passed: release validation 40159872972 (Linux
1,509 passed/93 skipped/2 xfailed, fresh wheel; Windows 1,422 passed/319 skipped,
actual EXE smoke), Windows regression 40159872925 (1,423 passed/318 skipped,
including packaging).

Frozen bank bytes unchanged (88b4c839171f07e25a51bd895ee66fd515efb05b90488e24244ba1ec3ee1339b):
336/336 cases, 48/48 HK labels/direct positives, all 144 foreign and 144
component/number negatives pass. Independent comparison: exactly two positives
TD/MY→HK and their four insufficient/contradictory counterparts TD/MY→unresolved;
other 330 full results and all direct matcher outputs unchanged. 155 assigned
new-global-baseline results remain protected with regional selection enabled.

Final private enabled/disabled runs: all three CSVs byte-identical to reviewed
rules6 baseline, 9,604 rows, 7,143 determined/2,419 inferred/42 unresolved,
zero changed codes/diagnostics and original fields/order/duplicates preserved.
No private inputs/outputs published. Remaining 42 are a separate accuracy task.

New local EXE 48,768,859 bytes, SHA256
3637ece9609602b5f6705b0c7a943703d774cc7d228db59f69655f9a9bbbb973,
actual offline frozen self-test passed. Wheel 198,259 bytes, SHA256
d4aceff11503c71ffcb8e4367d3e2ac481a104eadc4c3ff2cea3bdf63a81c8e4.
Detailed receipt: docs/COMPOUND_STREET_FIX_2026-10-25.md. Historical rules6
million timings remain labelled rules6, not reused as measurements of this fix.
