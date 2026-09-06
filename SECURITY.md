# Security policy

## Supported version

Security fixes are applied to the latest release on the default branch. The
current supported release is 0.3.x.

## Report a vulnerability privately

Do not put credentials, private feeds, personal data, or an exploitable proof
of concept in a public issue or discussion. Use GitHub's
[private vulnerability reporting](https://github.com/superwesleyhys-ux/factcircuit/security/advisories/new)
to contact the maintainer with:

- the affected version or commit;
- a concise description of the impact;
- the smallest safe reproduction you can provide; and
- any suggested mitigation.

Reports about ordinary accuracy regressions, incomplete evidence, or weaker
trace outcomes belong in the
[Accuracy decline discussion category](https://github.com/superwesleyhys-ux/factcircuit/discussions/categories/accuracy-decline).

## Credential handling

Model and provider credentials must be supplied through the process
environment or an external secret manager. Never commit `.env` files, API
keys, bearer tokens, private source material, or raw logs that contain them.
Treat any credential pasted into chat, an issue, a trace, or a terminal log as
exposed and rotate it immediately.

## Security boundary

FactCircuit is a research harness. Its cutoff gates, hashes, validation
contracts, and audit records make failures easier to inspect; they are not a
sandbox, a remote-source authenticity service, or a guarantee that a model has
forgotten knowledge acquired after a historical cutoff.
