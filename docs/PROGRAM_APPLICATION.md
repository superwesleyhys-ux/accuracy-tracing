# Codex for Open Source: application preparation

**Draft only. Not submitted.** This starter has not yet been published, and no external adoption or real-news performance is asserted here.

## Program facts

Checked September 5, 2026: OpenAI's [Codex for Open Source page](https://developers.openai.com/community/codex-for-oss) offers eligible maintainers six months of ChatGPT Pro with Codex through an application process. It invites core maintainers, widely used public projects, and projects that can explain an important ecosystem role. The page does not specify a guaranteed star threshold.

The [program terms](https://learn.chatgpt.com/docs/codex-for-oss-terms) describe selection factors including usage, ecosystem importance, active maintenance, maintainer role or permissions, and program capacity. An application does not guarantee acceptance; benefit availability, timing, and scope are subject to the terms. Creating a new repository alone does not establish eligibility.

Recheck the linked pages before submitting. This document is a preparation outline, not a reproduction of the official application form.

## Truthful project description

NewsVerify Harness is a new Python starter for an evidence-driven verification loop around news trackers. It accepts a claim with a time cutoff, requests evidence, performs mechanical citation and timestamp checks, groups related sources, and requests further evidence within explicit limits. It returns a policy outcome and an audit record.

The current version runs offline with synthetic fixtures and uses adapter- or human-supplied stance labels and provenance identifiers. It has not measured real-world news accuracy, implemented live retrieval, or demonstrated that iterative retrieval beats a single pass. The author's earlier private news tracker has not yet been integrated.

The intended public contribution is a small, reproducible harness that other maintainers can connect to their own retrieval systems, inspect, and evaluate. Public utility and adoption still need to be demonstrated.

## Proposed use of support

I would use Codex to maintain regression tests, review source-handling changes, improve adapter documentation, and develop reproducible evaluation tooling. Planned work includes one live adapter, better source-lineage handling, and an event- and time-separated benchmark comparing the loop with a single-pass baseline under an equal budget. I would publish measured results and limitations, including negative results.

## Complete with verifiable evidence

| Field | Entry to complete before submission |
| --- | --- |
| Applicant name and GitHub profile | [Insert verified identity and profile URL.] |
| Public repository | [Insert actual public repository URL after publication.] |
| Maintainer role and permissions | [Describe actual role; link commits or other public evidence.] |
| License and latest release | [Link MIT license and an actual tagged release.] |
| Reproducible demo and test run | [Link the released instructions and a real CI run.] |
| Maintenance activity | [Link actual issues, fixes, reviews, or releases with dates.] |
| External users or integrations | [Provide verifiable examples; state “none yet” if that is accurate.] |
| Project usage | [Provide measured counts, dates, and source; do not invent downloads or users.] |
| Ecosystem importance | [Explain demonstrated use and link supporting evidence; separate planned benefits.] |
| Evaluation results | [Link an actual report and protocol; identify synthetic results explicitly.] |

Keep the draft's current-state language until the corresponding work is actually complete. Do not describe intended contributors, integrations, accuracy gains, or community impact as established facts.
