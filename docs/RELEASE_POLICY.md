# Current formal deployment

The operator accepted manual testing on **25 October 2026** and requested that
this version be the sole formal deployment and uploaded to GitHub.

- **v0.2.0 is the only current supported formal application version.**
- GitHub Latest and the README download entry identify v0.2.0. Main contains
  the same released application source. Existing feature PRs are integrated
  rather than left as competing deployment sources.
- The canonical local executable is `D:\WASE\WorldAddressEngine.exe`, copied
  from the verified v0.2.0 artifact and checked against its SHA256. The generated
  `CURRENT_RELEASE.json` records its version, release URL and actual hash.
- Earlier releases/tags and local build folders remain historical audit and
  rollback material; they are not the active deployment. Do not overwrite or
  delete published history to make a new version current.
- Freeze the accepted business behavior from a99d94e / country rules7. Release
  preparation changes version identity, documentation and CI identity checks.
  Future behavior changes require a new requested development/release task,
  fresh validation and a new immutable release identity.
- Reference databases are separate versioned downloads. The optional Hong Kong
  source remains explicitly partial, with 9,508 excluded features and a verified
  receipt. A formal application release does not certify exhaustive source
  coverage, global accuracy, deliverability or signed strict-postal approval.
- Keep private inputs, row reports, plaintext checkpoints and benchmark oracles
  local and out of source control, CI and release assets.
