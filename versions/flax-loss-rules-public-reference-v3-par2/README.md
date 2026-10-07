# Current contributor task version — Flax v3 PAR-2

Updated 2026-10-07 UTC. **ACTIVE CONTRIBUTOR REVISION / locally execution validated / maintainer adoption and benchmark inclusion PENDING.** This identifies the contributor-selected task actually used by the ongoing local Docker run; it does not retroactively change the approved v2 proposal or imply organizer acceptance.

## Exact execution identity

- Frozen task commit: `bc20b17aff54847129ee2e458d152641ca39cac4`; scientific/retention freeze: `bab7bf4516fc4e7dec09fa90daf72a9456be5c97`. The later commit adds the system administration PATH entries needed by Work account setup, preserving scientific executable precedence.
- Protocol: `flax-loss-rules-public-reference-v3-par2`; metric: `stratum-normalized-par2-utility-v1`. Protocol SHA-256: `8d76ae59eaf5a127c8fb54b3e018ea621c61e1c24c0b48738e2decf5bbf2416c`.
- Directory/task name remains `flax-loss-rules-public-reference-v2`; candidate ABI `flax-loss-rules-v2` and loss ABI `compute_loss-v1` remain unchanged.
- Startup-repaired Base/Judge image: `sha256:ac51816905f41c4286d6af583f0866c19cd993a8a9ec5854770ae09b35c8a667`; prepared Work image: `sha256:f63ddc395bfc5836940f082237791b6c0f0e6a148695f5237022ada48716dc0d`.
- Complete reference validation used `sha256:795aa7e783c7454a07118d413d493b23e17de1606c80e06b67bc36e0e70b83df`. The startup-repaired image inherits that scientific evidence with targeted account-setup/executable-identity tests; the complete reference was not rerun on the repaired image.
- Compiler source, tests, environment and fixed-input hashes are recorded in `current-version.json`. The public task mirror and `source-inventory.json` identify the exact frozen bytes rather than a reimplementation.

## Primary objective and unchanged experiment

For a timely plan validated against the original PDDL, normalized cost is `t/T` and utility is `1-t/(2T)`. Ordinary no-plan, invalid-plan and deadline outcomes have cost 2 and utility 0, including early failures. Primary score is `100*(1-mean_strata(mean_case_costs)/2)`, equivalently 100 times the mean of the eight stratum mean utilities. It is bounded 0–100, higher is better; normalized cost is dimensionless, bounded 0–2, lower is better. Candidate-invalid, infrastructure and incomplete/inconsistent records remain unscored/null. Late validation cannot become a success. Harness transports the same 0–100 primary `reward`, never the legacy score or normalized cost.

Factor 2 is fixed task-owned configuration. Legacy utility `1-t/(10T)` remains a distinctly named secondary diagnostic, together with macro/micro/per-stratum coverage, timing and plan length. The PAR-2 failure-penalty principle has [SAT Competition 2024 precedent](https://satcompetition.github.io/2024/tracks.html); deadline normalization, stratum weighting, original-PDDL validation and infrastructure policy are task-specific adaptations.

This amendment was selected **after** observing reference results and the headroom block. It is a real objective change, not a unit conversion or preregistration. It gives latency five times the former successful-case sensitivity relative to coverage and can change rankings; higher utility need not mean higher coverage. No penalty-factor search, baseline weakening, new case selection or noise/significance claim is involved.

The experimental unit remains the loss/relaxation/complementary tuple. Work submits `loss.py`, `relaxation_rules.json`, `complementary_rules.json` and the existing nine-field `manifest.json`; any subset of the three components may change. Original positive-weight-10 node-mean BCE and both original pinned rule files remain the reference. Fixed interpreters/planning/recovery, cache/schema/order, 195 labels and 19/176 split, seed 0, 301 epochs, 3311 updates, 62 validation forwards, three loader workers, final checkpoint and fresh training for every scored tuple remain unchanged. All 400 cases, eight 50-case strata, 20/40-second deadlines and original-task VAL remain fixed. `PYTHONHASHSEED=0` precedes relevant interpreters. CPU-only: four logical CPUs, zero GPUs, threads one, separately requested Work/Judge 8 GiB; paused Work residency is not zero by assumption. No mandatory full Work training for rule-only development and no paired baseline in normal Judge.

## Complete contributor reference evidence

Reference run `893836454a26435f8c8095ec5607b7b3`, completed 2026-10-06, freshly trained and evaluated all 400 cases. Primary PAR-2 **77.0066810889938**, secondary legacy **85.60133621779876**, normalized PAR-2 cost **0.45986637822012394**; 351 valid, 48 deadline, one no-plan, zero invalid, macro/micro coverage **87.75%**. Full Docker invocation **5302.247522 seconds**, training 3311 updates and 62 validation forwards. Numerical headroom to 100 is **22.9933189110062 points**, not evidence of achievable improvement.

All authoritative records, valid plans, actual original-task VAL evidence, identities and inventory hashes survived normal container removal and were independently checked, with dual aggregation/algebra agreement within absolute tolerance 1e-10. Captured Judge cgroup peak was 1.759338 GiB under an 8-GiB limit; final approximately 11 seconds were unsampled. This is contributor-run evidence, not independent maintainer verification, continuous aggregate-node peak, a variance study or an optimized-method result. Required-compute projections are upper bounds; they do not demonstrate ten adaptive loops or resolve unknown future Work/transition cost.

Historical v1 score 85.4842811693254 and v2 score 85.89312505564187 remain historical PAR-10 observations. Original v2 headroom BLOCKED is unchanged; its missing authoritative per-case records remain unavailable. The new complete v3 run does not reconstruct them. The public v1 release, protocol, hashes and notices remain intact.

## Durable audit and research boundary

The supported lane is LOCAL Docker. `/logs/verifier/audit/<task-run-id>/` is backed by the operator's private persistent verifier-output bind. In Harness it resolves under `logs/runs/<Harness-run-id>/<task-name>/verifier/<submission>/audit/<task-run-id>/`, outside Work mounts. Atomic COMPLETE/PARTIAL markers and a hashed inventory distinguish complete and interrupted evidence; export failure remains infrastructure/unscored and does not delete the only surviving scratch evidence. Retained evidence includes case/timing/outcome/PDDL/tuple/checkpoint identities, available process diagnostics and actual plans/VAL evidence where produced. Persistent log I/O remains within the existing scored intervals; post-case export/fsync counts toward total trial time.

Research feedback remains sanitized aggregate/per-stratum diagnostics and permitted development feedback. Detailed primary audit, answer plans, native trajectories and credentials are not added to Work or ordinary Git commits. Public-source availability and shared same-user/root limitations remain; directory separation is not a security guarantee. Local container-cleanup tests do not prove power-loss, disk-loss or cluster persistence.

## Current research execution and formal reconciliation

The clean Sol research context runs through the bundled read-only RSI-Harness: run `3375bbffc2004b19a662de51904ce910`, Codex `gpt-6.1-sol` / `high`, existing local account. At 2026-10-07T03:09:20Z durable state was `judging`; no completed-run result is claimed here. The cumulative operator cap remains 24 hours including prior attempts, preparation, transitions and recovery; it was not reset for model replacement. Resolved Agent timeout was 80157.21733956781 seconds with unlimited-by-default submissions within that budget. Do not launch a duplicate run from this publication.

Maintainer adoption and benchmark inclusion remain pending. [Discussion #176](https://github.com/OpenRSI-Foundation/OpenRSI-Index/discussions/176) retains the historical approved v2 body. `proposal-v3-draft.md` is the exact versioned proposal handoff for the original proposal session to confirm/reread/update through its documented workflow; publishing this draft or a status comment does not itself amend the approved body, send `/task` or `/reset`, regenerate the task, or approve inclusion.

## Using this snapshot

`flax-loss-rules-public-reference-v2/` is a byte-identical mirror of the frozen task, including its original contextual documentation. Relative references in that frozen README point to the original local validation layout; use this version README for publication status and evidence summary. This mirror excludes the bundled Harness; use the generated private repository with its pinned read-only Harness for supported execution. A local Docker image ID is provenance, not a published registry image. No v3 release or registry publication is asserted. Original overlay and third-party license scopes remain as recorded in the task and the historical notices.
