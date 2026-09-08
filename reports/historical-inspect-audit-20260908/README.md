# Inspect replay audit

Inspect independently reproduced the original historical test's scores from its saved responses and receipts. **This is an offline scoring replay, with zero new model calls.** It is not a second model test.

| Evidence variant | Method | Cutoff matches, all runs | Completed runs | Authenticity abstentions | Later-false claims identified as false |
|---|---|---:|---:|---:|---:|
| Original | Direct | 4/4 | 4/4 | 2/2 | 0/2 |
| Original | Harness | 4/4 | 4/4 | 2/2 | 0/2 |
| Blinded | Direct | 3/4 | 3/4 | 1/2 | 0/2 |
| Blinded | Harness | 3/4 | 3/4 | 1/2 | 0/2 |

The two saved timeout failures remain in the denominator with zero credit. Both concern case `h07`; the harness's retained `unresolved` status does not earn abstention credit after a failed final call. All completed authenticity answers abstained, and all attribution controls matched their labels. The saved results show no score advantage for either method on these cases. Abstaining on insufficient contemporary evidence is not successful advance detection of fabrication.

The [optional replay script](../../experiments/historical-cutoff-20260908/inspect_replay.py) uses its own output-shape, completion, citation, and label checks. It reads the completed raw predictions, registered corpus and gold, and saved input/response/call sidecars. It does not import the original scorer or derive scores from its summary. The original summary is opened only afterward for comparison: all 16 rows across 11 compared fields and every aggregate agreed. Inspect's 32 aggregate metric values were also checked against its scored rows.

The audit ran four Inspect tasks using `model="none"`, a solver that copies previously saved outputs, and deterministic scorers. A runtime guard forbids `Model.generate`; it recorded zero attempted calls. Inspect logs contain zero model events and no model token usage. This replay records the original batch's 48 logical calls and two failed calls as historical data, not new activity.

Inspect version: `0.3.264.dev23+gec3bf0995`. Source commit: [`ec3bf0995fb6435f452f158f85ca423803aa0f98`](https://github.com/UKGovernmentBEIS/inspect_ai/tree/ec3bf0995fb6435f452f158f85ca423803aa0f98). The optional dependency was installed in a separate temporary environment; project dependencies and frozen inference files were unchanged. [Inspect model-free evaluations](https://inspect.aisi.org.uk/models.html) and [custom scoring](https://inspect.aisi.org.uk/custom-scorers.html) describe the framework interfaces used.

This is an independent implementation of the scoring checks, using the same evidence, gold labels and prior model outputs. It adds no independent event families, fresh inference, semantic adjudication, or image forensics. Original and blinded variants share four target propositions across two event families. It cannot prove that the original model lacked pretrained knowledge of later events, and exact quote integrity does not by itself prove semantic entailment.

[RESULTS.json](RESULTS.json) contains categorical and numeric audit results. [MANIFEST.json](MANIFEST.json) binds the public files, replay script, framework commit and source-artifact hashes. Full Inspect logs and raw evidence remain locally retained; their hashes are included without private paths or session identifiers. Replaying the actual batch requires those retained private artifacts. A public checkout can run the script's `--self-test` without Inspect, credentials, private evidence or network access.
