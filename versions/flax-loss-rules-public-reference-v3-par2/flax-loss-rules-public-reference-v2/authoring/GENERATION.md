# Generation record

Original generation (historical): Stages 7–8 only. The bound confirmation controls the package. Destination
`output/flax-loss-rules-public-reference-v2` was absent and rechecked immediately
before creation. No controller input was modified. Independent review and
execution validation are outside this invocation; correction count is zero.

## Evidence and static validation

The exact upstream and contributor release bytes were inspected without
execution. Release digests, the baseline tuple, original allocation order,
primary/development PDDL hashes, source patch, CPython source checksum, native
source identities, and dependency lock are preserved in this package.

Read-only `authoring/static_checks.py` verifies Harness prerequisites, Python
3.10 syntax, shell syntax, archive path/type/identity closure, package size,
baseline/pristine maps, unchanged 195/176/19/280/400/720 allocations, source/rule
identity, public/Judge separation, and public-helper parity. It never imports
or executes task modules. The combined skill validator is the authoritative
static/compiler check and uses `public-evidence/RSI-Harness`.

The initial read-only preflight passed. The initial combined validator found
one mechanical `PIP_UNPINNED` error: its token parser treated the separate
extra-index URL argument as a package. The equivalent `--extra-index-url=URL`
form resolved it without changing dependency pins. The repeated combined
validation passed with zero errors, zero warnings, and compiler success:
WORKDIR `/workspace`, Work/Judge GPUs 0/0, Agent 86,400 seconds, Judge 45,000
seconds. The supplied compiler source SHA-256 is
`8a36720888afdca07ea8b001b5f4ffc4aee0a6bcd4442280288d8d9d6707278f`.

## Single Generator review and closure

The destination was reconfirmed as this invocation's newly created task; all
edits remained under its exact output prefix. One combined Generator review
traced source identity, baseline restoration, post-build closure, admission,
training counts, both native rule engines, every child launch/stream, timed
GO-to-original-VAL flow, aggregation, cleanup, and all reward terminal paths.
It produced the following worklist, all closed before final validation:

- Early entrypoint/import exceptions could bypass safe feedback. The fixed
  launcher now converts startup failures to structured diagnostics without raw
  tracebacks; normal safe aggregate output remains streamed.
- Parent numerical imports needed explicit private cache/temp settings. The
  parent now uses its disposable private trial root before those imports; all
  children receive the same bounded per-process scratch policy.
- Callback mutation of graph value types could produce ambiguous Python errors.
  Type, identity, tensor version, shape, dtype, and value checks now return a
  specific candidate-input-mutation error. Persistent constants, closures,
  derivatives, and RNG state are also checked without extra model forwards or
  optimizer updates. Candidate runtime I/O is guarded; no arbitrary-code sandbox
  claim is made.
- Attributable native loss-process failures needed evidence beyond training
  stage. The fixed trainer records the current callback/derivative phase;
  recognized fatal signals in that phase follow candidate-invalid behavior.
  SIGKILL/OOM/unknown crashes remain infrastructure-unscored. Candidate-frame
  Python failures retain safe component/line/type diagnostics. IPC checks direct
  worker liveness, so inherited loader socket descriptors cannot hide a crashed
  trainer until the entire training deadline.
- Fixed-source checks now reject unexpected source files outside explicit
  native build-product directories and include the baked v2 reference tuple.
  Native source checks retain immutable identities, not machine-specific
  historical binary hashes.
- Public helper copies and their direct callers/build closure are synchronized
  with the authoritative Judge copies. Development paths expose only selected
  public cases, never the primary roster or Judge results.
- CPython's pinned install recipe uses host-wide `compileall -j0`. The Docker
  recipe changes only generated Makefile install parallelism to `-j4`; runtime
  interpreter source and version remain unchanged. Native builds also use four
  jobs, and all installs precede WORKDIR closure.

Terminal-path inspection: baseline and every admitted candidate take the same
fresh-training and 400-case route; candidate-invalid, ambiguous, incomplete,
startup, cleanup, dependency, and infrastructure paths create no reward;
ordinary search outcomes alone may contribute zero case utility; successful
aggregation and complete cleanup precede the only exclusive reward write.
Empty rule objects still reach the original planner stages; missing rule files
never fall back. Admission does not assert rule soundness or completeness.

Post-build inspection: all dependencies/native products are outside WORKDIR;
the final image initialization seeds four reference files and an empty research
directory, calls the same admission semantics, and compares a separate pristine
inventory. No subsequent build step writes WORKDIR. Runtime confirmation of
this design remains pending.

Final read-only checks: PASS. Final combined static/compiler validation: PASS,
zero errors and zero warnings, after all review edits and inspection of their
direct dependents. The validation commands are the task-owned
`authoring/static_checks.py --harness-root` command and the skill's combined
`validate_task.py --harness-root` command documented in README. This record does
not claim execution validation.

## Warning dispositions

- Four `SHARED_OUTPUT_UNDOCUMENTED` warnings for the baked v2 reference loss,
  relaxation rules, complementary rules, and manifest: fixed by documenting
  all four exact paths in the Agent instruction and their Solution/Judge
  relationship in README.
  Static/compiler warnings: none on the final clean validation.
- Judge-side fresh training: accepted, explicitly contributor-approved to avoid
  weight/selection confounding, including its iteration and full-validation cost.
- Loop capacity and aggregate memory: accepted as unmeasured/incomplete; retain
  the 24-hour default/48-hour option and avoid a fabricated budget flag.
- Historical v1 result: accepted as reported, unreproduced, protocol-mismatched
  context; preserve missing revision-2 helper-source caveats.
- Shared root runtime, public reference exposure, timing noise, and one seed:
  accepted limitations, disclosed without attestation/generalization claims.
- Stateful execution and independent review: not performed by the explicitly
  limited Stage 7–8 invocation; expensive checks remain pending.

## Pending execution

No environment build, project test, runtime self-check, training, evaluation,
baseline, Solution, GPU workload, or real Agent was executed. The maintainer
README lists the complete required execution-validation matrix and scientific
limitations. Static checks cannot certify baseline parity, memory, native build
behavior, timing, provider routing, noise, or adaptive-loop capacity.

## Controller-assigned correction round 1

The supplied INITIAL review requested changes on two implementation findings.
This invocation owns their corrections only, at the existing workflow-owned
`output/flax-loss-rules-public-reference-v2` destination. `run/` and all other
supplied inputs remain read-only. The confirmation and complete handoff were
read; the scientific contract, protocol bytes, manifests, resources, baseline,
reward, and failure classifications are unchanged. No new review was started.

1. **Fast Downward source closure — fixed.** The complete pinned checkout is
   now temporary build material outside `/opt/flax`. The Docker recipe exports
   that exact HEAD with `git archive`, extracts it at the original runtime path,
   and performs the unchanged bounded native build there. It removes the
   temporary checkout/archive. This applies the pinned upstream export policy
   instead of retaining export-excluded files and symlinks under the source
   gate. Neither authoritative manifest nor either runtime integrity gate was
   weakened or changed. Read-only official tree/archive comparison finds 1,770
   checkout blobs, 552 retained regular files matching every SHA-256 and Git
   blob identity, and 1,218 omitted blobs including all three source symlinks.
   Public/Judge runtime and manifest copies agree. Build-generated products
   remain under the existing `builds` exception. Real native build and
   untouched-container preflight remain execution-validator work.
2. **Actionable candidate training exceptions — fixed.** Both trainer copies
   use the same structured formatter for import, callback, derivative, and
   candidate-frame training exceptions. It preserves a bounded single-line
   message, exception type, operation, candidate source line/statement, and
   NameError/ImportError identifier when available. Callback/derivative errors
   also include public input shapes; derivatives include the scalar loss shape.
   Source locations map the private snapshot back to
   `/workspace/candidate/loss.py`; fallback callback-definition locations are
   explicitly labeled. Source reading respects Python's admitted encoding.
   No raw traceback, frame locals, primary case input, or new reward path is
   added. The parent retains the complete `CandidateInvalid` envelope through
   IPC and safe feedback. The public development consumer prints and appends
   that envelope to its already retained `training.log`.

Focused static diagnostic traces (no callback execution):

| Representative failure | Producer and retained repair information |
| --- | --- |
| `logits.square().mean() + missing_weight` | Callback handler retains NameError message/name, the candidate expression and its line, plus public input shapes. |
| Incompatible tensor operation | Callback handler retains the library's RuntimeError dimensions/message, candidate expression/line and input shapes; no tensor values are dumped. |
| `from torch import missing_symbol` | Import handler retains ImportError message/import name and the candidate import line. |
| Failed autograd operation | Derivative handler retains operation/message, shapes, and candidate frame or explicitly labeled callback definition. |

Direct dependents inspected: Docker export/build ordering and source gate;
matching public runtime; both training handlers, admission, launcher, IPC,
`safe_error`, Judge `child_error` and terminal handler; development output and
log lifetime. All candidate-invalid paths still leave reward absent; successful
training/exposure and scoring control flow are untouched. This is targeted
correction validation, not another independent review or a runtime claim.

Final affected checks are the task-owned `authoring/static_checks.py` with the
supplied Harness root, `authoring/check_native_closure.py`, and the skill's
combined `validate_task.py` with the same Harness root. Their initial corrected
invocations passed; they are repeated after the correction documentation edits.
The preflight parses 25 Python files and four shell entrypoints, checks frozen
data/baseline identity and public/Judge consistency, and statically traces the
diagnostic producers/consumers without importing any task module. Combined
validation reports zero errors, zero warnings, and compiler success with the
unchanged WORKDIR, GPU counts, and timeouts.

Warning dispositions carry forward: the four reference-path documentation
warnings remain fixed; contributor-approved Judge training, incomplete memory
and loop estimates, historical v1 protocol/source caveats, shared root runtime,
public exposure, timing noise, and single-seed limitations remain accepted.
The initial independent review has now occurred and identified these two
corrected findings; this record does not claim a re-review outcome. All review
residual execution risks remain pending, including build/cache/native/library
compatibility, unchanged-tuple parity, full training/evaluation, failure and
feedback paths, cleanup/timing, aggregate memory, and operator provider routing.
