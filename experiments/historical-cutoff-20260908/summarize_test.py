"""Score historical predictions only after inference; keep later gold separate."""
import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import runpy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HELPER_PATH = ROOT / 'experiments/gstack-harness-eval-20260908/summarize_test.py'
HELPERS = runpy.run_path(str(HELPER_PATH))
CONDITIONS = ('direct', 'double_loop')


def read(path):
    return HELPERS['read'](path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def audit_exposure(packet, case):
    pool = {m['version_id']: m for m in case['materials']}
    full, previews = [], []
    def walk(value):
        if isinstance(value, dict):
            if {'version_id', 'content', 'available_at'} <= set(value):
                require(value['version_id'] in pool and value == pool[value['version_id']], 'Unregistered material entered a model request')
                full.append(value['version_id'])
            if 'catalog' in value:
                require(isinstance(value['catalog'], list), 'Malformed source catalog')
                for entry in value['catalog']:
                    require(isinstance(entry, dict) and entry.get('version_id') in pool, 'Unregistered catalog source')
                    source = pool[entry['version_id']]
                    expected = {k: source[k] for k in ('version_id', 'url', 'issuer', 'published_at', 'available_at')}
                    expected['preview'] = source['content'][:800]
                    require(entry == expected, 'Source catalog metadata or preview differs from the registered source')
                    previews.append(entry['version_id'])
                require(len(previews) == len(set(previews)), 'Duplicate catalog source')
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    walk(packet)
    return {'full_material_ids': sorted(set(full)), 'catalog_preview_ids': sorted(set(previews)),
            'registered_materials_and_previews_only': True}


def summarize(out, gold_path):
    out = Path(out)
    manifest = read(out / 'manifest.json')
    predictions = read(out / 'stage-artifacts/predictions.json')
    corpus = read(out / 'corpus.json')
    preflight = read(out / 'preflight.json')
    registration = read(out / 'registration.json')
    require(manifest['test_stub'] is False and predictions['test_stub'] is False, 'Stub outputs cannot be scored as model results')
    require(manifest['worker_exit_code'] == 0 and all(manifest['frozen_integrity'].values()), 'Incomplete or changed inference batch')
    require(manifest['gold_loaded'] is False and predictions['gold_loaded'] is False, 'Gold isolation metadata failed')
    require(sha(out / 'corpus.json') == manifest['corpus_sha256'] == preflight['corpus_sha256'], 'Corpus hash mismatch')
    require(sha(out / 'preflight.json') == manifest['review_sha256'], 'Preflight hash mismatch')
    require(sha(out / 'registration.json') == manifest['registration_sha256'], 'Registration hash mismatch')
    require(registration['corpus_sha256'] == manifest['corpus_sha256'], 'Registration corpus mismatch')
    require(sha(gold_path) == registration['gold_sha256'], 'Prespecified gold changed after launch')
    require(sha(Path(__file__)) == registration['scorer_sha256'], 'Scorer changed after registration')
    require(sha(HELPER_PATH) == registration['helper_sha256'], 'Imported scoring helper changed after registration')
    require(datetime.fromisoformat(registration['registered_at']) <= datetime.fromisoformat(manifest['started_at']), 'Gold registration occurred after inference began')
    for name, expected in manifest['frozen_code_sha256'].items():
        require(sha(out / 'frozen-inputs' / name) == expected, 'Frozen source mismatch')
    gold = read(gold_path)
    cases = {c['target']['id']: c for c in corpus['cases']}
    labels = {g['id']: g for g in gold['cases']}
    require(len(cases) == len(corpus['cases']) == manifest['case_count'], 'Case denominator mismatch')
    require(len(labels) == len(gold['cases']) and set(labels) == set(cases), 'Gold denominator mismatch')
    runs = predictions['results']
    require(len(runs) == 2 * len(cases) and len({(r['id'], r['condition']) for r in runs}) == len(runs)
            and {(r['id'], r['condition']) for r in runs} == {(cid, arm) for cid in cases for arm in CONDITIONS}, 'Missing or duplicate condition')
    rows, receipts, stage_groups, exposure = [], [], defaultdict(list), []
    temporal = manifest['temporal_instruction']
    for run in runs:
        cid, arm = run['id'], run['condition']
        folder = out / 'stage-artifacts' / cid / arm
        require(read(folder / 'result.json') == run, 'Result sidecar mismatch')
        case, label = cases[cid], labels[cid]
        score = HELPERS['score_run'](run, case, {'expected_fact_status': label['cutoff_expected']})
        valid = score['pipeline_success'] and score['citations']['passed']
        observed = run['fact_status']
        raw_final = score.get('final_output')
        final = raw_final if isinstance(raw_final, dict) else {}
        text = json.dumps(final, ensure_ascii=False)
        # This detects explicit future references only, not every possible memory leak.
        future_mentions = sorted(set(re.findall(r'\b20(?:2[4-9]|[3-9]\d)\b', text)))
        row = {'id': cid, 'condition': arm, 'event_family': label['event_family'],
               'role': label['role'], 'variant': label['variant'], 'observed': observed,
               'raw_verdict': score['raw_verdict'], 'cutoff_expected': label['cutoff_expected'],
               'future_expected': label['future_expected'], 'pipeline_success': score['pipeline_success'],
               'citation_integrity': score['citations']['passed'], 'valid': valid,
               'cutoff_match': bool(valid and observed == label['cutoff_expected']),
               'future_verdict_match': bool(valid and observed == label['future_expected']),
               'abstained': bool(valid and observed == 'unresolved'),
               'accepted_later_false_claim': bool(valid and label['role'] == 'authenticity' and observed == 'supported'),
               'called_later_false_claim_false': bool(valid and label['role'] == 'authenticity' and observed == 'contradicted'),
               'unwarranted_settled_cutoff_verdict': bool(valid and label['cutoff_expected'] == 'unresolved' and observed != 'unresolved'),
               'errors': run['errors'], 'logical_calls': len(run['calls']),
               'timer_seconds': run['timer_seconds'], 'clock_discrepancy': score['clock_discrepancy'],
               'explicit_future_years_in_final_output': future_mentions,
               'mechanisms': score['mechanisms'], 'citations': score['citations'],
               'rationale': final.get('rationale'), 'final_output': final,
               'usage': HELPERS['token_stats'](run['calls'])}
        rows.append(row)
        require(len(run['calls']) <= (1 if arm == 'direct' else 10), 'Logical call limit exceeded')
        report_io = (run.get('report') or {}).get('execution', {}).get('model_io', [])
        if arm == 'double_loop' and run.get('report'):
            require(len(report_io) == len(run['calls']), 'Harness response audit has a different call count')
        verified_response = None
        for n, call in enumerate(run['calls'], 1):
            stem = folder / f"{n:02d}-{call['stage']}"
            require(read(stem.with_suffix('.calls.json')) == [call], 'Call sidecar mismatch')
            item = read(stem.with_suffix('.input.json'))
            response_path = stem.with_suffix('.response.json')
            require(not call.get('test_stub'), 'A stub invocation appeared in a model batch')
            if call['success']:
                require(response_path.is_file(), 'Successful call is missing its model response')
            response = read(response_path) if response_path.is_file() else None
            if arm == 'direct' and response is not None:
                require(response == run.get('raw_response'), 'Scored direct answer differs from its response receipt')
            if arm == 'double_loop' and report_io:
                audit = report_io[n - 1]
                require(audit['packet'] == item['packet'] and audit['schema'] == item['schema'], 'Harness report input differs from its recorded request')
                require(item['instructions'] == temporal + '\n' + audit['instructions'], 'Harness instruction audit differs from actual request')
                if response is not None:
                    require(audit.get('response') == response, 'Harness report response differs from its receipt')
            if call['stage'] == 'verify' and call['success']:
                verified_response = response
            require(item['instructions'].startswith(temporal), 'Temporal instruction missing from an actual call')
            require(call['model'] == 'gpt-6-astra' and call['reasoning_effort'] == 'medium' and call['tunnel'] == 'local', 'Arm settings differ')
            require(call['timeout_seconds'] == 90, 'Deadline differs')
            exposed = audit_exposure(item['packet'], case)
            serialized = json.dumps(item['packet'], ensure_ascii=False)
            require('cutoff_expected' not in serialized and 'future_expected' not in serialized, 'Gold field appeared in inference')
            receipt_id = f"{cid}:{arm}:{n:02d}"
            receipts.append({'id': receipt_id, 'case_id': cid, 'condition': arm, 'ordinal': n,
                'stage': call['stage'], 'model': call['model'], 'reasoning_effort': call['reasoning_effort'],
                'tunnel': call['tunnel'], 'success': call['success'], 'status': call['status'],
                'wall_seconds': call['wall_seconds'], 'usage': call.get('usage'),
                'local_skills_disabled': call.get('local_skills_disabled'),
                'input_sha256': sha(stem.with_suffix('.input.json')),
                'response_sha256': sha(stem.with_suffix('.response.json')) if stem.with_suffix('.response.json').exists() else None,
                'original_receipt_sha256': sha(stem.with_suffix('.calls.json'))})
            stage_groups[arm, call['stage']].append(call)
            exposure.append({'receipt_id': receipt_id, **exposed})
        if valid and arm == 'double_loop':
            require(isinstance(verified_response, dict), 'A completed harness result needs a recorded verifier response')
            require(all(final[key] == verified_response[key] for key in ('verdict', 'rationale')), 'Scored harness verdict differs from its final model response')
            basis = [{k: b[k] for k in ('version_id', 'quote')} for b in final['basis']]
            require(basis == verified_response['basis'], 'Scored harness citations differ from final model response')
    aggregate = {}
    for variant in ('original', 'blinded'):
        aggregate[variant] = {}
        for arm in CONDITIONS:
            selected = [r for r in rows if r['variant'] == variant and r['condition'] == arm]
            authentic = [r for r in selected if r['role'] == 'authenticity']
            controls = [r for r in selected if r['role'] == 'attribution_control']
            aggregate[variant][arm] = {
                'cases': len(selected), 'completed': sum(r['pipeline_success'] for r in selected),
                'evidence_valid': sum(r['valid'] for r in selected),
                'cutoff_matches': sum(r['cutoff_match'] for r in selected),
                'authenticity_cases': len(authentic),
                'accepted_later_false_claims': sum(r['accepted_later_false_claim'] for r in authentic),
                'called_later_false_claims_false': sum(r['called_later_false_claim_false'] for r in authentic),
                'authenticity_abstentions': sum(r['abstained'] for r in authentic),
                'unwarranted_settled_cutoff_verdicts': sum(r['unwarranted_settled_cutoff_verdict'] for r in authentic),
                'controls': len(controls), 'control_matches': sum(r['cutoff_match'] for r in controls),
            }
    conditions = {arm: HELPERS['token_stats']([c for r in runs if r['condition'] == arm for c in r['calls']]) for arm in CONDITIONS}
    summary = {'model': manifest['model'], 'reasoning_effort': manifest['reasoning_effort'], 'tunnel': 'local',
        'cutoff': gold['evidence_cutoff'], 'event_families': gold['event_families'],
        'cases': len(cases), 'runs': len(runs), 'conditions': conditions,
        'scores_by_variant': aggregate, 'rows': rows,
        'stages': [{'condition': arm, 'stage': stage, **HELPERS['token_stats'](calls)} for (arm, stage), calls in sorted(stage_groups.items())],
        'explicit_future_year_audit': 'Screening only; absence of an explicit later year does not prove absence of pretrained knowledge.',
        'source_text_scope': 'Text extracted from historical originals; no visual image-forensics capability is tested.',
        'future_score_scope': 'A contradicted verdict can match later truth without being justified by cutoff evidence. Abstention is not successful advance detection.',
        'manifest_sha256': sha(out / 'manifest.json'), 'gold_sha256': sha(gold_path),
        'scorer_sha256': sha(Path(__file__)), 'helper_sha256': sha(HELPER_PATH),
        'frozen_input_checks_passed': True, 'exposure': exposure}
    dump(out / 'SUMMARY.json', summary)
    dump(out / 'SANITIZED_RECEIPTS.json', {'receipts': receipts})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=HERE / 'results')
    parser.add_argument('--gold', type=Path, default=HERE / 'private/gold.json')
    args = parser.parse_args()
    result = summarize(args.results, args.gold)
    print(json.dumps({k: result[k] for k in ('event_families', 'cases', 'runs', 'conditions', 'scores_by_variant')}, indent=2))
