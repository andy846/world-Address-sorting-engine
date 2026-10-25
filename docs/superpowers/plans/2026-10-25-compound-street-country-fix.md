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
- [ ] Full regression; unchanged frozen public bank all labels pass; private
  enabled/disabled replay and quantify every code/status change locally.
- [ ] Commit/push existing Draft PR, remote CI and rebuilt Windows EXE smoke.

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
