# Co-design learning objectives and symbolic abstraction rules

**DRAFT / LOCAL AMENDMENT / MAINTAINER CONFIRMATION PENDING — updated 2026-10-06.** The contributor selected fixed-factor PAR-2 after inspecting the completed v2 reference results and the validator headroom block. This local approval is not maintainer approval or retrospective preregistration. The accepted remote task and original evidence remain unchanged. One fresh complete local Docker reference of the combined metric and retention version has now completed; maintainer adoption remains pending.

Optimize Flax's validated planning efficiency with a two-deadline failure penalty by changing a stateless learning objective, declarative relaxation rules, complementary rules, or any combination.

## Goal

- Test falsifiable hypotheses about how supervised object scores and abstraction affect valid planning.
- Compare each tuple under the same frozen training, planner, workload, deadlines, and original-task validation.
- Record useful negative findings and stratum tradeoffs. Rule-only improvement is legitimate; tuple improvement alone does not establish component effects or synergy.

## Workspace

| Item | Value |
| --- | --- |
| Working directory | `/workspace` |
| Candidate | `/workspace/candidate/loss.py`, `/workspace/candidate/relaxation_rules.json`, `/workspace/candidate/complementary_rules.json`, `/workspace/candidate/manifest.json` |
| Development work | `/workspace/research/` for hypotheses, scripts, logs, and unscored checkpoints |
| Fixed source | `/opt/flax` |
| Public inputs | `/opt/flax-assets` contains the frozen label cache, ordered schema, training/validation/development manifests, and original reference components |
| Starting state | Editable copies of positive-weight-10 node-mean BCE and the original two rule files, with a valid manifest |

Only the four candidate files are scoring inputs. Do not add extra entries to `/workspace/candidate` or extra top-level entries to `/workspace`. Development artifacts cannot extend the callback's dependencies or permissions. Judge reloads closed, flushed file bytes from the read-only workspace snapshot; no Work process, cache, checkpoint, or self-score is authoritative.

## Reference baseline

| Item | Value |
| --- | --- |
| Baseline | Positive-weight-10 node-mean BCE with the original relaxation and complementary rules, available under `/opt/flax-assets/reference-v2` |
| Reported result | Historical loss-only/original-tuple v1 score 85.4842811693254; 350/400 valid, 49 deadlines, one no-plan |
| Parent v2 measurement (legacy metric) | Unchanged reference tuple: 85.89312505564187; 352/400 valid, 47 deadlines, one no-plan, zero invalid plans; full Judge invocation 5176.278624 seconds, fresh training 737.601371 seconds |
| Status | Repository-local Docker validator measured the complete v2 workload on 2026-10-05; runtime checks passed, validator readiness is blocked by its 20-point headroom criterion. This is one reference measurement, not a formal Agent run or a variance study. Historical publication caveats remain. |
| Historical PAR-2 projection | Aggregate-only projection 77.46562527820936; historical per-case rescore remains BLOCKED because parent raw records were not retained |
| New combined-version reference | Run 893836454a26435f8c8095ec5607b7b3, 2026-10-06: PAR-2 primary 77.0066810889938; legacy secondary 85.60133621779876; normalized cost 0.45986637822012394; 351/400 valid, 48 deadlines, one no-plan, zero invalid plans; macro/micro coverage 87.75%; fresh 3311 updates and 62 validation forwards; full Docker Judge 5302.247522 seconds |
| Local validation | Persistent complete-record verification and independent dual-metric aggregation passed within 1e-10; numerical headroom 22.9933189110062 points. Required-compute floor projection passes, while actual adaptive Work/cycle costs remain unmeasured. Original v2 status and maintainer adoption are unchanged. This single reference is not a candidate improvement or variance study. |
| Comparison | A separate unchanged-tuple submission establishes the target-environment baseline. Each normal submission scores only its own tuple; there is no live paired baseline. |

To restore the starting tuple, copy `/opt/flax-assets/reference-v2/loss.py`,
`/opt/flax-assets/reference-v2/relaxation_rules.json`,
`/opt/flax-assets/reference-v2/complementary_rules.json`, and
`/opt/flax-assets/reference-v2/manifest.json` into their corresponding
`/workspace/candidate` files. The reference copies themselves stay fixed.

## Research loop

1. Inspect the reference, public development cases, and prior safe feedback. State one falsifiable hypothesis.
2. Edit any subset of the loss and two rule components. Keep all three files present and update their manifest digests.
3. Run `/usr/local/bin/validate-candidate --json`. It reads only public/candidate data and checks paths, file inventory, digests, static rules, and loss syntax. It neither trains nor proves runtime validity.
4. Use public development computation as needed. `/usr/local/bin/flax-dev train --out /workspace/research/attempt-01` freshly trains the current tuple's loss with the fixed recipe and retains a snapshot. `/usr/local/bin/flax-dev plan --training /workspace/research/attempt-01 --case-id "$DEV_GROUP_ID"` runs exactly the explicitly selected `group_id` from `/opt/flax-assets/manifests/development.json`. Set `DEV_GROUP_ID` to that actual identifier. Development logs/plans are detailed and unscored. Use a new attempt directory to preserve history.
5. Close and flush the four candidate files, then submit with `rsi-submit`. Inspect prior summaries using `rsi-submit --list`.
6. Compare aggregate evidence, retain all failures, and keep, revise, or reject the hypothesis.

Judge-owned fresh training is an explicit part of this experiment: a selected Work checkpoint would confound objective changes with weight/selection choices. Every scored tuple, including rule-only candidates, trains afresh. This consumes submission time and reduces iteration capacity. Work checkpoints are development artifacts only.

## What you may change

The manifest has exactly nine fields: `candidate_id`, `abi_version`, `description`, `loss_path`, `loss_sha256`, `relaxation_rules_path`, `relaxation_rules_sha256`, `complementary_rules_path`, `complementary_rules_sha256`. Use ABI `flax-loss-rules-v2`, a string description, and an ID matching `[A-Za-z0-9_-]+`. Each path is exactly its relative filename (`loss.py`, `relaxation_rules.json`, `complementary_rules.json`), with its actual 64-hex SHA-256 digest. Files must be regular, not links; no unknown fields or duplicate JSON keys. Rule order and raw bytes are preserved, not normalized. Each submitted file is bounded to 1 MiB; rule/index collections have documented parser bounds of 1024 entries.

### Loss

`compute_loss(logits, targets, graph, *, epoch, step)` uses the original logits, targets, raw node/edge features, and graph metadata, and returns one finite scalar differentiable with respect to the original logits. Use installed numerical libraries and pure calculations. No input mutation, retained adaptive state, validation-call adaptation, RNG-state changes, optimizer control, additional model passes, or runtime filesystem/environment/network/service lookups. The trainer owns initialization, forwards, backward, optimizer, and final checkpoint selection. Static checks and counted-call mutation/state/derivative checks enforce practical invariants; they do not constitute an arbitrary-code sandbox.

### Rule vocabulary

| Predicate family | Signature |
| --- | --- |
| `onground`, `clear`, `isheavy`, `islight`, `ismoveable` | obstacle |
| `dirisup`, `dirisdown`, `dirisleft`, `dirisright` | robot |
| `posempty` | pos |
| `upon` | obstacle, obstacle |
| `holding` | robot, obstacle |
| `rat` | robot, pos |
| `oat` | obstacle, pos |
| `upto`, `downto`, `leftto`, `rightto` | pos, pos |
| `handempty` | nullary |

Use these lowercase names, argument positions, binding slots, and runtime relations only. No case/object constants, filenames, answer tables, per-stratum selection, or executable rule callbacks. Reject unsupported shapes, fields, arities, bindings/types, non-JSON constants, boolean indices, and negative indices.

### Relaxation

An ordered object of nonsemantic rule labels; each value has exactly `pre_compute`, `precond`, `delete_objects`, `delete_effects`, and `add_effects`. The predicate-indexed sections are objects; `delete_objects` is an integer list.

- `pre_compute` contains two valid argument-position selectors for its predicate. Unary self-maps work; nullary maps do not. Original-state literal iteration forms object-to-object maps with last assignment winning; no join or uniqueness is imposed.
- Every `precond` entry is an independent trigger. Selected argument positions seed slots with those same indices; entries are alternatives, not a conjunction.
- `delete_objects` consumes already seeded slots before effects.
- Unary deletion consumes a bound slot. Ordered binary deletion may derive an unbound slot using that predicate's precomputed map keyed by binding slot 0, with compatible anchor/result types. Missing map entries skip that deletion without inventing a binding. Any later object/unary-delete/add consumption of an unset slot is candidate-invalid. Runtime checks are inside the case timer.
- Additions are unary and consume bound slots. Effect indices denote binding slots, so the reference `posempty:[1]` is valid.
- Goal objects are protected from object/literal deletion; unary additions have no extra goal guard. Final cleanup removes literals referencing deleted objects.

### Complementary rules

Each predicate entry has exactly `cond` and `cmpl`, equal-sized outer lists of length one or two, containing valid argument-position lists. Empty inner lists retain their meaning. The first pass (outer length one) adds complements when the original selected set is disjoint from the condition objects. The second (outer length two) uses intersection with that original set. Newly added objects do not become a condition set and there is no transitive closure. Missing facts do not fire.

Both interpreters match original-state literals. Empty top-level `{}` objects are supported and all planner stages still execute. Admission does not establish abstraction soundness, completeness, or solvability.

## What stays fixed

- The frozen 195-label cache, ordered first-19 validation/remaining-176 training split, feature schema, and original data/manifests. Candidate rules never change labels or training inputs. No teacher calls, new/replacement examples, extra tasks, data collection, or trained-weight initialization.
- Seed 0 with startup `PYTHONHASHSEED=0`; 301 epochs, batch 16, no shuffle, three DataLoader workers, Adam 1e-3; 23 node features, 24 edge features, three message-passing steps, layer size 16, zero dropout; final-epoch weights.
- Exactly 3,311 optimizer updates, 52,976 training graph exposures, 31 validation phases, 62 validation forwards, 589 validation graph exposures, and 3,373 callback calls.
- Fixed FD `lama-first`, threshold decay, iteration limits, 40-second inner timeout with its original allocation/control flow, goal protection, pruning/relaxation/complementary/recovery algorithms, and original domain/actions/problems/goals. No planner or interpreter changes.
- Fixed source, interpreters/libraries, reference assets, optimizer, architecture, evaluator, and resource policy are prohibited modification targets. No forged metrics or validation.
- Four allocated logical CPU IDs, numerical threads one, three training loaders, one serial planning worker, 8 GiB per phase, zero GPUs. All task runtime networks are disabled; no research web search, remote inference, teachers, scoring, or remote execution. Platform model-provider access does not permit candidate services.

## Evaluation and feedback

Exactly 400 ordered cases, 50 per stratum across 12×12/15×15 × easy/medium/hard/expert, use a fresh worker/guider and the same admitted rule pair. The 280 development cases and 720 unused groups stay unchanged. No dropping, replacement, favorable reruns, renormalization, or reuse of trained weights.

The external monotonic clock starts immediately before GO. Graph construction, inference, rule matching and binding checks, temporary-state/problem creation, planning/recovery, plan IPC, and independent original-instance VAL completion all count. Only interpreter/model loading and original-PDDL parsing may precede GO; they still count toward the whole trial. External deadlines are 20 seconds for 12×12 and 40 seconds for 15×15. A plan validated after the deadline receives zero utility.

The proposed primary metric is `stratum-normalized-par2-utility-v1` under protocol `flax-loss-rules-public-reference-v3-par2`, parent `flax-loss-rules-public-reference-v2`. The directory/task name and candidate ABI `flax-loss-rules-v2` remain unchanged; loss ABI is `compute_loss-v1`. The fixed task-owned failure factor is **2**, independent of BCE's positive weight 10 and never a candidate field.

For case i, frozen deadline T and scored elapsed t include final original-task VAL. A valid plan with `t <= T` has dimensionless normalized cost `t/T` and utility `1-t/(2T)`. Ordinary `no_plan`, `invalid_plan`, and `deadline` have cost 2 and utility 0 even when they terminate early. Candidate-invalid, infrastructure, incomplete, duplicate/missing/extra, wrong-identity or contradictory records stay unscored (`primary_score: null`, preserved status/reason, no reward artifact). A purported valid record with late, negative or nonfinite elapsed is rejected, never clamped into success.

`normalized_par2_cost = mean_strata(mean_cases(t/T if timely valid else 2))` is dimensionless, bounded [0,2], **lower is better**. `primary_score = reward = 100*(1-normalized_par2_cost/2) = 100*mean_strata(mean_case_utilities)` is bounded [0,100] in score points, **higher is better**, theoretical ceiling 100. All eight manifest strata receive equal weight; no per-case rounding. Equivalent aggregations use absolute tolerance 1e-10, without relaxing outcome/deadline checks. Harness transports the same 0–100 `reward` scalar; no 0–1 mapping.

The former utility is equivalently `1-c_old/10`, with normalized PAR-10-style cost `c_old=t/T` for timely valid cases and 10 for ordinary failures. It therefore awarded timely successes 90–100% of maximum utility. The former `1-t/(10T)` utility is retained only as `legacy_par10_utility_score` on identical records. Report macro/micro validated coverage, per-stratum counts/coverage/timing, successful-only latency and plan length (null when undefined), and normalized PAR-2 cost. `failure_penalized_mean_seconds` retains its historical ONE-deadline failure penalty; it is a separate timing diagnostic, not PAR-2 cost. Safe feedback adds protocol/metric identities and these aggregate fields without exposing primary cases or audit traces.

[The SAT Competition 2024 tracks page](https://satcompetition.github.io/2024/tracks.html) supplies precedent for charging runtime to solved instances and twice the timeout to unsolved ones. Per-instance deadline normalization, equal-stratum macro weighting, original-PDDL validation and unscored infrastructure are task-specific adaptations. This is not the exact SAT implementation or an OpenRSI-mandated metric. The objective gives validated planning efficiency more weight in joint loss/rule optimization while retaining a failure penalty. Coverage remains diagnostic; higher utility can accompany lower coverage or stratum regressions. This changes candidate rankings rather than merely converting units.

On this 400-case 8×50 roster, each case contributes 0.25 times its utility in score points. Failure-to-valid conversion contributes about 0.125–0.25 points. A one-second change in an otherwise valid 20-second case changes score by 0.00625 points; for 40 seconds, 0.003125 points. Timing sensitivity is five times the old metric's and the near-cutoff success/failure jump is smaller. These are formula sensitivities, not estimated noise or significance thresholds. Overall noise direction is unmeasured. Conditional confirmation uses balanced serial trials of a fixed candidate tuple and reference with complete records and all attempts retained; no favorable-run selection. Reliability claims need coverage evidence; joint-component synergy needs corresponding controls. Those trials require separate authorization.

The retained parent feedback identifies source run `f784a5ffe6c14a46923cde7b3b4cc652`, original v2 execution protocol SHA-256 `6fd1cceed8c8660fabd4b886a24d1ebb2ee3e815f3f6d44126ffb73d87356a64`, with macro coverage 0.88. Its arithmetic projection `5*85.89312505564187 - 400*0.88` is **77.46562527820936**, implying dimensionless cost **0.4506874944358128** and ceiling-100 headroom **22.53437472179064**. **These are aggregate-only projections, not verified per-case rescoring or an amended reference execution.** All 400 authoritative raw case records were transient and deleted by the parent evaluator; the retained monitor captured tensors/training/resources, not these records. Actual rescored primary score/cost remain null. Neither an older run nor reconstructed times were substituted. See [parent rescoring status](../../flax-loss-rules-par2-20261005-01/derived/rescoring-status.json).

The original v2 numerical condition remains unmet (14.10687494435813 points); its validator status remains BLOCKED. Runtime 5176.28 s and the ~16.7-loop projection belong to the parent execution. Its aggregate-only PAR-2 projection remains retrospective and unverified per case. The separate combined-version run reported above measures the new local baseline and passes the bundled numerical headroom condition without a waiver; this does not establish achievable improvement, timing significance, or maintainer adoption. Persistent worker/VAL log writes and readbacks remain inside the unchanged GO/VAL interval and may affect latency; record export, fsync, aggregation and cleanup also count toward total runtime. Actual Judge overhead is included in the new full measurement. The observed required public-admission Work floor is 0.081749138 seconds; optional research-agent work, Harness transitions and paused-Work/aggregate-node memory remain unmeasured. The current ~16.3-loop required-compute projection is an upper bound, not observed adaptive cadence. No policy exception was applied.


Invalid manifest/rules/loss/model, candidate-attributable execution or training-budget failures are candidate-invalid and unscored. Ambiguous crashes, corrupt fixed assets, dependency/evaluator/VAL failures, startup/cleanup failure, whole-evaluation guard expiry, and incomplete records are infrastructure-unscored. Both report primary_score null and leave no reward artifact; neither becomes a completed zero score. The narrow externally late negative-residual timeout-125 path is an ordinary deadline; unexplained pre-cutoff 125 is infrastructure failure.

Visible feedback contains status, current protocol/metric identity, current primary score/reward, dimensionless normalized PAR-2 cost, explicitly named legacy score, per-stratum counts/coverage/timing, safe diagnostics, resources, and safe tuple/trial provenance. Successful-only timing/plan length is null when undefined; failure-penalized timing uses the deadline as a penalty, not an observed completion time. Candidate errors identify the absolute component path, field, code, and repair condition. Primary case identities/paths, individual outcomes, answer plans, raw tracebacks, and audit traces are excluded from Judge feedback. Detailed diagnostics require explicitly selected development cases. Judge retains its detailed evaluation evidence under a private `/logs/verifier` host bind for operator audit. That archive is neither a Work mount nor additional research feedback. Missing/corrupt exports are infrastructure-unscored; partial/interrupted archives do not establish completed trials. This local Docker retention repair does not establish durability on the native cluster backend.

Harness exposes the full safe Judge stdout/stderr stream and a footer with round, status, reward, exit code, timeout, duration, remaining submissions, and errors; score appears when available. This public-reference protocol offers no unseen-holdout guarantee. Repeated aggregate feedback can permit adaptive overfitting. Seed-0 and noisy timings do not establish across-seed robustness or a measured gain. Root-capable Work and inherited runtime state remain limitations.

Training guard: 3,600 seconds; READY: 60; cleanup: 5 plus 0.5 seconds liveness; evaluation: 38,300; complete trial: 41,900; Judge timeout: 45,000. Agent time is 86,400 seconds and includes synchronous Judge waits and transitions; an operator may extend it to 172,800. Historical training took 809.914954 seconds and a full local v1 trial 5218.769735 seconds; neither is a v2 guarantee. Complete-loop capacity remains an incomplete estimate. Ten adaptive loops are a planning target, not a demonstrated cadence or submission cap.

## Submission checklist

- All four files exist, contain the intended hypothesis, have matching hashes, and are closed/flushed.
- `/usr/local/bin/validate-candidate --json` accepts the public static contract.
- Only candidate/research paths changed; no Work state is needed by Judge.
- Preserve every attempt and failure; do not select favorable repeated trials.
- Interpret small timing gains, cutoff flips, and stratum regressions cautiously. Any later matched-repeat or component/interaction analysis needs a separately declared plan retaining all results.
