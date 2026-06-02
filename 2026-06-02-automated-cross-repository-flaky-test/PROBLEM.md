## Automated Cross-Repository Flaky Test Root-Cause Attribution and Prioritized Self-Healing for CI/CD Pipelines

**Problem statement:** Engineering teams have no production-ready, cross-stack tool that automatically detects flaky CI tests, attributes each failure to its specific non-deterministic root cause (timing, concurrency, environment, or state leakage), and proposes targeted code-level fixes — leaving teams to manually re-run pipelines, guess at causes, and silently accumulate test-suite rot.

**Who experiences this problem:** Software engineering and QA teams of all sizes that rely on CI/CD pipelines — from startups running GitHub Actions to large enterprises using Jenkins or GitLab CI — experience this daily, especially as test suites grow and parallelism increases. The problem compounds for AI-augmented teams generating higher volumes of tests faster than they can stabilize them.

**How frequently:** 
The proportion of teams experiencing test flakiness grew from 10% in 2022 to 26% in 2025, while pipeline complexity increased by 23% over the same period
 — meaning teams encounter cascading false failures on nearly every push cycle.

**Why current solutions are insufficient:** 
While LLMs show promise for automatically repairing flaky tests, existing approaches like FlakyDoctor fail in industrial settings due to the "context problem" — providing either too little context or too much irrelevant information to the model.
 
Analysis from QA Wolf found that DOM changes and brittle selectors account for only about 28% of test failures — yet most self-healing tools only target this narrow category — while more than 70% are due to timing issues, test data problems, runtime errors, and rendering failures.
 
A 2025 State of QA report found that test maintenance, including fighting flakiness, consumes roughly 40% of QA team time — time not spent finding bugs, but fighting the testing infrastructure itself.


**Why software can solve this:** 
Detecting flaky tests relies on pattern recognition and signal analysis across run histories; the process involves identifying recurring patterns, classifying failures, and correlating environment telemetry to separate true regressions from noise
 — all tasks well-suited to automated ML pipelines with access to CI execution data. 
Research prototype FlakyGuard, which treats code as a graph and uses selective graph exploration for context, successfully repaired 47.6% of reproducible flaky tests with 51.8% of fixes accepted by developers — outperforming prior approaches by at least 22%
 — demonstrating the tractability of this approach at scale.

**Estimated impact if solved:** 
A 2025 analysis found that flaky test failures consume over 8% of total development time, adding up to roughly $120,000 in lost productivity per year for a team of 50 engineers.
 
According to the 2025 State of DevOps Report, teams with high test flakiness rates experience 40% slower deployment frequency compared to teams with stable test suites
 — making reliable, automated remediation a direct accelerant for software delivery velocity at scale.

**Sources:**
- https://testdino.com/blog/flaky-test-benchmark (Flaky Test Benchmark Report 2026, with Bitrise/Google/Microsoft/Atlassian data)
- https://arxiv.org/abs/2511.14002 (FlakyGuard: Automatically Fixing Flaky Tests at Industry Scale, ASE 2025)
- https://www.functionize.com/blog/the-flaky-test-problem-root-cause-and-how-ai-solves-it (Functionize, April 2026, citing FSE 2025 and Reproto 2025 analyses)
- https://www.desplega.ai/blog/deep-dive-17-foundation-hidden-cost-flaky-tests (2025 State of DevOps Report citation on deployment frequency impact)
- https://getautonoma.com/blog/flaky-tests (Autonoma State of QA 2025 Report)