# Development instructions

These instructions apply to this subtree. Follow applicable parent instructions and the user's current request. In an existing repository, merge these rules with its AGENTS.md rather than replacing project-specific rules.

## Start with the working path

- Read the entrypoint, configuration, domain implementation, integration layer and relevant existing checks before editing.
- Identify the smallest user-visible result and implement one complete path from input to reusable output.
- Use existing modules and dependencies. Change shared infrastructure only when a concrete second implementation needs it.
- Keep unknown upstream APIs explicit. Inspect the pinned source or run a small experiment; do not invent compatible signatures.
- Preserve unrelated edits and supported historical artifacts. Do not push, publish or deploy unless requested.

## Responsibilities

| Layer | Owns |
| --- | --- |
| Domain package | Data preparation, algorithm adapters, common evaluation, selection, portable models and inference |
| Algorithm adapter | Native options, execution, native-to-common conversion, equivalence checks and resource cleanup |
| Shared core | Small records, existing IO/config utilities and genuinely shared artifact conventions |
| Integration layer | External SDKs, data/model retrieval, orchestration, upload, presentation and application lifecycle |
| Entrypoints/scripts | Argument handling and calls into the layers above |

- Domain and core code must run without the orchestration SDK.
- Adapters return candidates; they do not rank other algorithms, publish models or read selection/final targets.
- Keep local and remote execution on the same domain functions.
- Reporting consumes results. It does not recompute scores, choose models or change coefficients.

## Keep the design small

- Prefer functions, small dataclasses and one explicit registry over deep inheritance or dynamic plugin discovery.
- Add a type when it prevents a real mistake at a boundary. Use plain dictionaries for algorithm-specific metadata.
- Validate user input and external results at boundaries; do not repeat identical checks in every function.
- Keep one source for parameter names, defaults and artifact keys. Do not introduce aliases or duplicate codecs.
- Make one complete input-to-output configuration example work before adding more options. Keep all examples consistent with the same API and serialized format.
- Specify ambiguous array shapes, column ordering, missing values, status values and path resolution at the boundary; do not create a new validation framework to describe them.
- Do not create placeholder adapters, speculative result types, a general workflow engine, a diagnostic framework or a universal constraint language.
- A new algorithm should normally require its adapter, registry entry, optional dependency/environment and one meaningful integration example.
- New output semantics may need an explicit small schema extension. Do not force posterior or multi-output results into a scalar point-model contract.

## Scientific and model correctness

- Freeze data partitions once. Fit preprocessing and search only on training data; use selection data for choosing candidates; use final data only after the choice and fit policy are fixed.
- Data preparation may check final-partition integrity, but must not precompute final model metrics or pass final targets into discovery.
- Keep repeated measurements of the same experiment/design together when the evaluation goal requires it. State any deliberately different split objective.
- Compare all candidates using the same rows, units, weights and common runtime. Native scores remain diagnostics.
- Check that exported models reproduce native predictions. Preserve protected operators, normalization, variable order and full-precision parameters.
- Separate fixed literals/physical constants from trainable parameters. Never silently refit fixed exponents or conversion constants.
- Keep native models immutable when creating refitted variants. Preserve the link to the original candidate.
- Do not report sampled constraints as global guarantees, generated probabilities as physical confidence, or empirical fit as causal discovery.
- Preserve invalid rows and failure reasons. Never improve a score by dropping a candidate's difficult rows.

## Optional libraries and pretrained assets

- Import optional libraries only in the selected adapter. Keep inference of portable scalar models independent of search libraries and checkpoints.
- Record dataset/split identity, resolved config, code/dependency version, seed and checkpoint/index hashes once; reuse that provenance.
- Resolve external assets outside the numerical domain. Use pinned local assets for normal runs; do not silently fetch a new checkpoint.
- Do not silently truncate features, change data, reduce candidate budgets or substitute an engine after failure.
- Release CPU pools, subprocesses and GPU resources. Use the existing runner for timeouts.
- Preserve Bayesian posterior semantics. A common least-squares refit is a separate point-estimation experiment.

## Errors and diagnostics

- Use ordinary exceptions for invalid configuration and infrastructure failure.
- Return structured engine failure only when the caller explicitly supports partial comparison.
- Save a short status/reason, useful counts and timings. Add detailed logs or large ledgers only for an observed debugging need.
- Reuse artifact writers; do not add an ID/hash/file for every intermediate object.
- Write model bundles atomically. Check only the compatibility and integrity needed to load them safely.

## Verification proportional to the change

- Run the repository's existing required gates and checks relevant to changed behavior.
- Add regression coverage for actual bugs and boundary risks: data leakage, native/export mismatch, fixed constants, invalid domains, and save/load predictions.
- Keep network downloads, large datasets, checkpoint loading, GPU search and stochastic performance benchmarks outside fast tests.
- A real adapter needs one small native-to-portable example. Parametrize shared assertions instead of copying a full test suite for each library.
- Do not test dataclass fields, registry lists or function internals merely to mirror the implementation. Avoid exact-string assertions for equivalent equations.
- Do not require a new algorithm to recover one exact expression in a short random search. Use numerical behavior and a separately budgeted benchmark.
- Existing required gates take precedence over these defaults. Do not skip them to meet a preferred duration.
- State exactly what ran, what passed, what was skipped and why. Never infer runtime/UI acceptance from reading code alone.

## Delivering a change

- Update the authoritative specification and usage example when public behavior changes; remove conflicting instructions.
- Summarize the result, main design decision, validation and remaining material limitations.
- Separate implemented behavior from proposed extensions. Leave unverified adapters unavailable by default.
