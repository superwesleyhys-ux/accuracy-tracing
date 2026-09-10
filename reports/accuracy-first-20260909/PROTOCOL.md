# Wastewater full-evidence diagnostic

This is an accuracy-first diagnostic on two previously exposed development cases from one event family: h05 (data-authenticity claim) and h06 (attribution control). It is not a holdout, a balanced authenticity benchmark, a fake-detection accuracy estimate, or evidence of superiority. The attribution control is not affirmative authentication of the underlying measurements. Preserve all earlier corpora and results.

## Fixed comparison

PLAN.json fixes h05/h06, fresh direct and news_tracing arms, and claim research mode. Each case has the unchanged excerpt and full accepted-manuscript text versions from the original frozen corpus. The supervisor verifies the full eight-case corpus hash but projects only h05/h06, in that order, into the isolated worker. Each arm runs once; order alternates: h05 direct then harness, h06 harness then direct. Four outcomes remain the denominator, including failed or invalid outcomes. No selective retries or replacement of a failed batch.

Both arms use local Codex-login HTTP with gpt-6-astra, medium reasoning, and at most 90 seconds per logical invocation. Local denotes the CLI route to hosted inference, not local model weights. The direct arm has one call; the harness has 24 shared calls, of which at most 10 are formal tracing calls. The logical batch ceiling is 50 calls. Case deadlines are 120 and 2190 seconds. There are no orchestration retries, no API-route fallback, and no source-network calls. Internal CLI retries are not independently controlled or counted as separate logical calls.

## Evidence change and limits

Every research invocation receives every supplied eligible text version completely, with version_id, URL, title, full content, context_excerpt=false, start=0, end=content_length=the exact character count, published_at, retrieved_at, available_at and availability_basis. Same-URL versions remain distinct versions of one source, not independent corroboration. The total capacity is 240000 characters; over-capacity input fails before an invocation rather than truncating. The exact EVIDENCE_SCOPE wording is committed and audited independently.

The direct and formal arms retain the unchanged canonical full pool and eligibility rules. Full supplied-text coverage does not mean the original experiment's raw measurements, figure images or unsupplied attachments are present. No new original source, missing table, figure, image, or biological material is added. The separate live-HTML table-extraction fix is not exercised by this snapshot corpus. Forecast improvement is not assumed: the formal verifier already had full manuscript text before this change.

Claim mode retains source research and synthesis while explicitly omitting irrelevant causal/timeline/presentation phases. Bounded research advice may guide formal source inspection but remains untrusted proposals; it cannot become quote evidence or settle gaps. Missing independent records do not justify a false verdict.

## Freeze, isolation and scoring

Before live inference, freeze PLAN.json, this protocol, current executable inventory, driver and scorer; register those hashes with the unchanged original corpus, gold, helper and independent-review hashes. The original preflight hash is also pinned. The worker is denied the original repository, full corpus, output, preflight, registration and private roots. It receives only selected non-biological cases and frozen inference code. Every request gets the original temporal rule and exact historical_target. No gold contents or scorer are copied into the worker.

After all four outcomes are archived, the scorer audits every actual request, response, schema and receipt against the canonical packet, scope, native research schema, bounded advice, source membership, clock limits and sidecar hashes. Only after that audit may the supervisor scorer parse the original future gold. Primary validity requires the whole pipeline to complete and the unchanged exact-quote grounding checks to pass. Formal-only validity is a separate diagnostic. An error cannot earn abstention or detection credit. Source and raw-model prose remain private.

Report exact original cutoff agreement and later-verdict agreement separately, with called-false, unresolved, accepted, conflicting and failed/invalid outcomes distinct. Tokens, stage shares, cached input and latency are descriptive diagnostics, not the optimization target. Unknown usage remains unknown, with measured lower bounds preserved; cached input is already included in input tokens. Model training memory is not erased by a temporal packet boundary.

## Separate manual diagnostic review

After scoring, independently inspect all retained research outputs against the supplied archive metadata. Record whether research correctly retains the canonical pre-cutoff availability, avoids asking for an archive already supplied, and distinguishes absent original measurement/figure records from archive existence. Automated exact-request coverage checks do not by themselves establish that the model understood those dates. Manual findings are reported separately and do not alter the original grounding, cutoff or future labels. No paid model judge.

A changed input/source version or label requires a separately registered diagnostic. This batch does not relax evidence thresholds or establish new holdout readiness.
