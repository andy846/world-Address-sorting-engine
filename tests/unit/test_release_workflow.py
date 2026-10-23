"""Static guardrails for the gated alpha release workflow."""

from pathlib import Path
import json
import re

import pytest


WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "publish-alpha-release.yml"
).read_text("utf-8")


def test_release_can_be_started_from_a_branch_push_with_an_explicit_marker():
    assert "[publish-alpha1]" in WORKFLOW
    assert "github.event_name == 'push'" in WORKFLOW
    assert "github.event.head_commit.message" in WORKFLOW


def test_alpha_zero_is_checked_before_alpha_one_is_published():
    assert "v0.1.0-alpha.0" in WORKFLOW
    assert "41497d682207c945a1fb54fcb8d4d9155cbdad7f" in WORKFLOW
    assert "26283" in WORKFLOW


def test_release_asset_set_and_database_contents_are_exact():
    assert "expected_names" in WORKFLOW
    assert "SQLite format 3" in WORKFLOW
    assert "WorldAddressEngine.exe" in WORKFLOW
    assert "SHA256SUMS.txt" in WORKFLOW


def test_reference_pack_hashes_are_anchored_to_reviewed_values():
    assert "f4ef044e94aa3d206f8fce1fa3e0d7ab5f03d6081d142fd7f9e8cf5837ab1b3f" in WORKFLOW
    assert "70d617a532b8faedd7d9703c9b952945f101334907df5936725123d20be1f70f" in WORKFLOW


def test_release_jobs_require_the_full_branch_ref():
    assert WORKFLOW.count('refs/heads/feat/hkp-trilingual-phase1') >= 3
    assert 'GITHUB_REF_NAME' not in WORKFLOW


def test_draft_creation_is_separate_from_upload_and_verified_by_release_id():
    create = WORKFLOW.index('id: publish_draft')
    upload = WORKFLOW.index('gh release upload')
    assert create < upload
    assert 'releases/tags/$TAG' not in WORKFLOW
    assert 'releases/$RELEASE_ID' in WORKFLOW


def test_downloads_are_compared_against_the_preupload_manifest():
    for directory in ('verify-draft', 'verify-published'):
        assert f'cmp release-assets/SHA256SUMS.txt {directory}/SHA256SUMS.txt' in WORKFLOW


def test_failed_or_cancelled_publication_is_returned_to_draft_by_id():
    assert 'always() && !success()' in WORKFLOW
    assert 'gh api --method PATCH' in WORKFLOW
    assert '-F draft=true' in WORKFLOW


@pytest.mark.parametrize('replace_digest', [False, True])
def test_alpha_zero_verification_rejects_a_same_size_replacement(
    tmp_path, monkeypatch, replace_digest
):
    block = WORKFLOW.split('Refuse to continue unless alpha.0 remains intact', 1)[1]
    script = re.search(r"python - <<'PY'\n(.*?)\n          PY", block, re.S)
    assert script is not None
    source = '\n'.join(line[10:] for line in script.group(1).splitlines())
    wheel_digest = '6f4fbc2db125be5294781d6d2cdf697fad104ab7219e2d1234c05dc38b38e40b'
    payload = {
        'tagName': 'v0.1.0-alpha.0', 'isDraft': False, 'isPrerelease': True,
        'targetCommitish': '41497d682207c945a1fb54fcb8d4d9155cbdad7f',
        'assets': [
            {'name': 'world_address_sorting_engine-0.1.0a0-py3-none-any.whl',
             'size': 26283, 'digest': 'sha256:' + ('0' * 64 if replace_digest else wheel_digest)},
            {'name': 'SHA256SUMS.txt', 'size': 122,
             'digest': 'sha256:e71aa553e5349952a6853594629c45cfe11384ba309057c1f6537b42211c858d'},
        ],
    }
    (tmp_path / 'alpha0-release.json').write_text(json.dumps(payload), 'utf-8')
    monkeypatch.chdir(tmp_path)
    if replace_digest:
        with pytest.raises(AssertionError):
            exec(compile(source, '<alpha0-workflow>', 'exec'), {})
    else:
        exec(compile(source, '<alpha0-workflow>', 'exec'), {})
