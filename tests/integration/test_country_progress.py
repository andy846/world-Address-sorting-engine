"""Synthetic coverage for count-only country runner events."""
import csv
import json

import pytest

from tests.unit.test_retrieve import geo
from world_address_engine.jobs import country_analysis as job


def source(tmp_path, rows=3):
    path = tmp_path / 'synthetic.csv'
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['ID', 'Address'])
        for number in range(rows):
            writer.writerow([f'SYNTHETIC_RECIPIENT_{number}', 'Japan'])
    return path


OPTIONS = {'address_columns': ['Address'], 'record_id_column': 'ID'}


def stages(events):
    return list(dict.fromkeys(event['stage'] for event in events))


def assert_count_only(events):
    for event in events:
        assert {'stage', 'processed', 'committed'} <= event.keys()
        assert event.keys() <= {'stage', 'processed', 'committed', 'total', 'status_counts'}
        for key in ('processed', 'committed', 'total'):
            if key in event:
                assert type(event[key]) is int and event[key] >= 0
        if 'total' in event:
            assert event['processed'] <= event['total']
        if 'status_counts' in event:
            assert event['status_counts'].keys() <= {'DETERMINED', 'INFERRED', 'UNRESOLVED'}
            assert all(type(count) is int and count >= 0
                       for count in event['status_counts'].values())
    assert 'SYNTHETIC_RECIPIENT' not in json.dumps(events)
    assert 'Japan' not in json.dumps(events)


def test_stage_order_first_record_before_commit_and_export_verification(tmp_path, monkeypatch):
    data, pack, out = source(tmp_path), geo(tmp_path), tmp_path / 'out'
    events, legacy, streams = [], [], []
    actual_records = job._records

    def track_records(*args):
        streams.append(args[0])
        return actual_records(*args)

    def event_received(event):
        events.append(event)
        if event['stage'] == 'classifying' and event['processed'] == 1:
            assert event['committed'] == 0
            assert not list((out / '.country-state').glob('*.jsonl'))
            assert legacy == []
        if event['stage'] in ('exporting', 'finalizing'):
            assert not (out / 'Run_Manifest.json').exists()
        if event['stage'] == 'complete':
            assert (out / 'Run_Manifest.json').exists()
            assert not (out / '.country-state').exists()

    monkeypatch.setattr(job, '_records', track_records)
    result = job.analyze_job(data, out, pack, OPTIONS, on_event=event_received,
                             on_progress=legacy.append)
    assert stages(events) == ['validating', 'hashing_input', 'hashing_pack', 'loading',
                              'restoring', 'classifying', 'verifying_sources',
                              'exporting', 'finalizing', 'complete']
    classification = [e for e in events if e['stage'] == 'classifying']
    assert any(e['processed'] == 1 for e in classification)
    assert 'total' not in classification[0]
    assert classification[-1]['processed'] == classification[-1]['total'] == 3
    exported = [e for e in events if e['stage'] == 'exporting']
    assert exported[0]['processed'] == 0
    assert any(e['processed'] == 1 for e in exported)
    assert exported[-1]['processed'] == exported[-1]['total'] == 3
    assert events[-1]['processed'] == events[-1]['committed'] == 3
    assert events[-1]['status_counts'] == result['status_counts']
    assert legacy == [3]
    assert len(streams) == 2  # Classification and export only; no count scan.
    assert_count_only(events)


def test_legacy_callback_without_events_still_reports_only_commits(tmp_path):
    legacy = []
    result = job.analyze_job(source(tmp_path, 5), tmp_path / 'out', geo(tmp_path),
                             OPTIONS, batch_size=2, on_progress=legacy.append)
    assert legacy == [2, 4, 5]
    assert all(type(count) is int for count in legacy)
    assert result['total_records'] == 5


@pytest.mark.parametrize('cancel_stage', ['classifying', 'restoring', 'exporting', 'finalizing'])
def test_cancellation_at_stage_is_resumable(tmp_path, cancel_stage):
    data, pack, out = source(tmp_path, 5), geo(tmp_path), tmp_path / 'out'
    events, legacy = [], []
    cancelled = False

    def on_event(event):
        nonlocal cancelled
        events.append(event)
        if event['stage'] == cancel_stage and event['processed'] >= 1:
            cancelled = True

    kwargs = dict(on_event=on_event, cancel_requested=lambda: cancelled,
                  on_progress=legacy.append)
    if cancel_stage == 'restoring':
        paused = job.analyze_job(data, out, pack, OPTIONS, batch_size=2, max_batches=1)
        assert paused['run_status'] == 'PAUSED'
        result = job.resume_analysis(out, **kwargs)
        assert legacy == []
        assert result['committed_records'] == 2
    else:
        result = job.analyze_job(data, out, pack, OPTIONS, **kwargs)
        assert result['committed_records'] == (0 if cancel_stage == 'classifying' else 5)
    assert result['run_status'] == 'CANCELLED'
    assert events[-1]['stage'] == 'cancelled'
    assert not (out / 'Run_Manifest.json').exists()
    assert (out / '.country-state' / 'config.json').exists()
    resumed_events = []
    resumed = job.resume_analysis(out, on_event=resumed_events.append)
    assert resumed['total_records'] == 5
    assert resumed['run_metadata']['address_columns'] == ['Address']
    assert resumed_events[-1]['stage'] == 'complete'
    assert_count_only(events + resumed_events)


def test_paused_event_and_restore_counts_preserve_committed_callback(tmp_path):
    events, legacy = [], []
    out = tmp_path / 'out'
    result = job.analyze_job(source(tmp_path, 5), out, geo(tmp_path), OPTIONS,
                             batch_size=2, max_batches=1, on_event=events.append,
                             on_progress=legacy.append)
    assert result['run_status'] == 'PAUSED'
    assert events[-1]['stage'] == 'paused'
    assert events[-1]['processed'] == events[-1]['committed'] == 2
    assert legacy == [2]
    assert 'complete' not in stages(events)
    events.clear()
    job.resume_analysis(out, on_event=events.append, on_progress=legacy.append)
    restored = [e for e in events if e['stage'] == 'restoring']
    assert restored[0]['processed'] == 0
    assert any(e['processed'] == 1 for e in restored)
    assert restored[-1]['processed'] == restored[-1]['total'] == 2
    assert all(e['committed'] == 2 for e in restored)
    assert legacy == [2, 4, 5]


def test_fast_stages_emit_first_and_end_without_per_record_flood(tmp_path, monkeypatch):
    monkeypatch.setattr(job, 'monotonic', lambda: 0.0, raising=False)
    out = tmp_path / 'out'
    job.analyze_job(source(tmp_path, 60), out, geo(tmp_path), OPTIONS,
                    batch_size=40, max_batches=1)
    events = []
    job.resume_analysis(out, on_event=events.append)
    for stage, first, last in [('restoring', 1, 40), ('classifying', 41, 60),
                                ('exporting', 1, 60)]:
        updates = [e for e in events if e['stage'] == stage]
        assert len(updates) <= 3
        assert any(e['processed'] == first for e in updates)
        assert updates[-1]['processed'] == last


def test_slow_classification_updates_are_throttled_to_four_hz(tmp_path, monkeypatch):
    now = 0.0
    actual_classify = job.CountryClassifier.classify

    def classify(classifier, record):
        nonlocal now
        now += 0.05
        return actual_classify(classifier, record)

    monkeypatch.setattr(job, 'monotonic', lambda: now, raising=False)
    monkeypatch.setattr(job.CountryClassifier, 'classify', classify)
    events = []
    job.analyze_job(source(tmp_path, 30), tmp_path / 'out', geo(tmp_path), OPTIONS,
                    on_event=lambda e: events.append((now, e)))
    for stage in ('classifying', 'exporting'):
        timed = [(t, e) for t, e in events if e['stage'] == stage and e['processed'] > 0]
        assert len(timed) >= 4
        # First positive count and forced end can bypass the time limit.
        for (earlier, _), (later, _) in zip(timed[:-2], timed[1:-1]):
            assert later - earlier >= 0.25 - 1e-9


def test_zero_rows_has_stage_end_counts_and_no_legacy_commit(tmp_path):
    events, legacy = [], []
    result = job.analyze_job(source(tmp_path, 0), tmp_path / 'out', geo(tmp_path),
                             OPTIONS, on_event=events.append, on_progress=legacy.append)
    assert result['total_records'] == 0
    assert legacy == []
    assert events[-1]['stage'] == 'complete'
    assert all(e['processed'] == e['committed'] == 0 for e in events)
    assert [e for e in events if e['stage'] == 'exporting'][-1]['total'] == 0
    assert_count_only(events)


@pytest.mark.parametrize('resume', [False, True])
@pytest.mark.parametrize('columns', [[], ['Address']])
def test_completed_metadata_keeps_selected_columns_without_row_values(tmp_path, columns, resume):
    data, out, pack = source(tmp_path), tmp_path / 'out', geo(tmp_path)
    options = dict(OPTIONS, address_columns=columns)
    if not columns:
        # Standard headers allow the existing automatic mapping contract.
        data.write_text('ID,NAME_ADDRESS_LINE1\nSYNTHETIC_RECIPIENT,Japan\n', encoding='utf8')
    result = job.analyze_job(data, out, pack, options, batch_size=1,
                             max_batches=1 if resume else None)
    if resume:
        result = job.resume_analysis(out)
    assert result['run_metadata']['address_columns'] == columns
    assert 'SYNTHETIC_RECIPIENT' not in json.dumps(result['run_metadata'])
    assert 'Japan' not in json.dumps(result['run_metadata'])
