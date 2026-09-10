# Luna reliability-gated policy comparison

This is a new policy round after the prior Luna run exposed repeated harness failures. The change was substantive: each harness case was capped at four logical calls and failed closed after a stage failure, with no extension rescue. Both arms used GPT-5.6 Luna, low reasoning, the local Codex-login route, and the same fixed eight-case historical package.

The run completed 16 planned rows. Direct completed all 8 calls (164,838 known tokens). The reliability-gated harness completed 15 calls (193,547 known tokens), with several rows still failing.

The original variant had direct 0/4 evidence-valid and 0/4 cutoff matches; harness had 1/4 evidence-valid and 1/4 cutoff match, but only 1/4 cases completed. The blinded variant had direct 0/4 evidence-valid and 0/4 cutoff matches; harness had 2/4 evidence-valid and 2/4 cutoff matches, with only 2/4 cases completed. Later-false detection was 0 for both arms. Because the harness lost execution completeness and did not improve the later-false endpoint, this does not establish superiority over Luna.

The full outputs are retained at `experiments/luna-reliability-20260910/results-reliability/`. No same-policy rerun is planned; any next round must change the decision policy again and use a fresh registration.
