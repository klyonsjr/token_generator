# Implementation Plan: Store Token in YAML File

## Overview

Add a YAML output to the `broker-token` CLI alongside the existing JSON output. Implementation proceeds bottom-up: declare the PyYAML dependency, add the guarded import, implement the two new pure/near-pure helpers (`resolve_yaml_path`, `write_yaml_token_file`), then wire them into `main()` orchestration, adding property-based and example tests close to each unit. The existing `write_token_file` (JSON) stays unchanged. Language: Python (matching the existing codebase), tests with `pytest` + `Hypothesis`.

## Tasks

- [x] 1. Declare the PyYAML dependency
  - [x] 1.1 Add PyYAML to `pyproject.toml` and `requirements.txt`
    - Add `"pyyaml>=6.0"` to the `[project].dependencies` list in `pyproject.toml` (pinned minimum version)
    - Add `pyyaml>=6.0` to `requirements.txt` with a specifier consistent with `pyproject.toml`
    - _Requirements: 6.1, 6.2_

  - [x] 1.2 Write config/smoke tests for the dependency declarations
    - Read `pyproject.toml`; assert a `pyyaml` entry with a `>=` minimum-version specifier is present in `[project].dependencies`
    - Read `requirements.txt`; assert a `pyyaml` line whose specifier matches the one in `pyproject.toml`
    - Assert `import yaml` in the test environment does not raise (R6.3)
    - Group in a new class (e.g. `TestDependencyDeclaration`), imports inside test methods
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 2. Add the guarded PyYAML import to the CLI
  - [x] 2.1 Add a guarded `import yaml` in `broker_token/cli.py`
    - Wrap `import yaml` in a `try/except ImportError` that prints a clear "PyYAML is required but not installed" message to `sys.stderr` and calls `sys.exit(1)`
    - Place the guard at module top (or in `main()` before path resolution) so a missing library yields a clean CLI error rather than a traceback
    - _Requirements: 6.4_

  - [x] 2.2 Write edge-case test for missing PyYAML
    - Simulate `ImportError` for `yaml` (e.g. monkeypatch `sys.modules`/import machinery); assert a stderr message is produced and exit is non-zero
    - _Requirements: 6.4_

- [x] 3. Implement YAML output path resolution
  - [x] 3.1 Implement `resolve_yaml_path(json_path, yaml_arg)` in `broker_token/cli.py`
    - If `yaml_arg` is provided and non-blank, return it unchanged (override precedence, R3.3)
    - If `yaml_arg` is empty or whitespace-only, raise `ValueError` (invalid override, R3.5)
    - Otherwise derive from the final path segment (basename): if the basename contains a `.`, replace from its last `.` to the end with `.yaml`; if not, append `.yaml` to the full path — directory portion unchanged (R3.1, R3.2)
    - If the resolved path equals `json_path`, raise `ValueError` (collision, R3.4)
    - Keep the function pure (no I/O, no printing); it raises `ValueError` for invalid cases
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Write property test for path derivation
    - **Property 5: YAML path derivation from the JSON path**
    - **Validates: Requirements 3.1, 3.2**
    - Tag: `# Feature: store-token-in-yaml-file, Property 5: For any JSON path with no override, if the final segment contains a '.', the derived YAML path equals the JSON path with the last-dot-to-end of that segment replaced by '.yaml'; otherwise '.yaml' is appended; directory portion unchanged`
    - Generate JSON paths with dotted and dotless basenames and nested directories; assert derivation rule holds and directory preserved; >=100 iterations
    - _Requirements: 3.1, 3.2_

  - [x] 3.3 Write property test for override precedence
    - **Property 6: A non-blank override path takes precedence**
    - **Validates: Requirements 3.3**
    - Tag: `# Feature: store-token-in-yaml-file, Property 6: For any JSON path and any non-blank YAML override argument, resolve_yaml_path returns the override argument unchanged, regardless of the JSON path`
    - Generate arbitrary JSON paths and non-blank overrides; assert `resolve_yaml_path` returns the override; >=100 iterations
    - _Requirements: 3.3_

  - [x] 3.4 Write edge-case tests for path collision and invalid override
    - Collision (R3.4): override equal to `json_path` raises `ValueError`
    - Invalid override (R3.5): `''`, `'   '`, `'\t'` each raise `ValueError`
    - Group in a class (e.g. `TestResolveYamlPath`), imports inside test methods
    - _Requirements: 3.4, 3.5_

- [x] 4. Implement the YAML writer
  - [x] 4.1 Implement `write_yaml_token_file(path, token_data)` in `broker_token/cli.py`
    - Wrap the fields under a single top-level `token` key and serialize with `yaml.safe_dump({"token": token_data}, default_flow_style=False, sort_keys=False)` so the YAML file parses back to `{"token": Token_Data}` (R1.2)
    - Create a temp file via `tempfile.mkstemp(dir=os.path.dirname(path) or ".")` in the destination directory
    - `os.chmod` the temp file to `0o600` before it becomes visible (R4.1); if `chmod` raises, delete the temp file and re-raise a permission error (R4.2)
    - `os.replace(temp_path, path)` to atomically overwrite any existing file (R1.6)
    - On any exception, remove the temp file in cleanup so no partial/truncated destination file remains, then re-raise (R1.5, R5.3)
    - Function raises on failure and never prints; all messaging/exit codes live in `main()`
    - _Requirements: 1.2, 1.6, 4.1, 4.2, 5.3_

  - [x] 4.2 Write property test for YAML round-trip
    - **Property 1: YAML round-trip preserves Token_Data**
    - **Validates: Requirements 1.1, 1.2**
    - Tag: `# Feature: store-token-in-yaml-file, Property 1: For any Token_Data mapping of string keys to string values, writing it with write_yaml_token_file then parsing with yaml.safe_load produces a mapping equal to {"token": Token_Data} — a single top-level 'token' key whose value equals the original Token_Data`
    - Generate `Token_Data` as a dict over the known field names to `st.text()` values (empty, unicode, YAML-significant chars `: # -` quotes, leading/trailing whitespace); write, `yaml.safe_load`, assert `yaml.safe_load(...) == {"token": token_data}`; >=100 iterations
    - _Requirements: 1.1, 1.2_

  - [x] 4.3 Write property test for overwrite
    - **Property 3: YAML write overwrites any existing file**
    - **Validates: Requirements 1.6**
    - Tag: `# Feature: store-token-in-yaml-file, Property 3: For any two Token_Data values A and B, writing A then B to the same YAML path leaves the file parsing to {"token": B} with no residual keys or values from A under the 'token' key`
    - Generate two `Token_Data` values; write A then B to same path; assert the file parses to `{"token": B}` with no residual A keys under `token`; >=100 iterations
    - _Requirements: 1.6_

  - [x] 4.4 Write property test for owner-only permissions
    - **Property 7: YAML file has owner-only permissions**
    - **Validates: Requirements 4.1**
    - Tag: `# Feature: store-token-in-yaml-file, Property 7: For any Token_Data, after write_yaml_token_file completes successfully on POSIX, the file permission bits equal 0o600`
    - Write, `os.stat`, assert `stat.S_IMODE(mode) == 0o600`; `pytest.mark.skipif` on non-POSIX; >=100 iterations
    - _Requirements: 4.1_

  - [x] 4.5 Write edge-case tests for YAML write and permission failures
    - YAML write failure (R1.5, R5.3): monkeypatch `yaml.safe_dump` (or `os.replace`) to raise; assert the destination YAML path does not exist and no partial file remains; assert the writer re-raises
    - Permission failure (R4.2): monkeypatch `os.chmod` to raise; assert the destination file is absent and a permission-related error is raised
    - Group in a class (e.g. `TestWriteYamlTokenFile`), imports inside test methods, use `tmp_path`
    - _Requirements: 1.5, 4.2, 5.3_

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Add the CLI argument and redaction constant
  - [x] 6.1 Add `--yaml-file`/`-y` argument and `REDACTION_MARKER`
    - Add `parser.add_argument("--yaml-file", "-y", default=None, help=...)` to the existing `argparse` parser in `main()`; leave `--token-file`/`-o` (default `token.json`) untouched (R2.2)
    - Define module-level `REDACTION_MARKER = "***REDACTED***"` for any output that would otherwise carry a `Sensitive_Field` value (R4.4)
    - _Requirements: 3.3, 2.2, 4.4_

  - [x] 6.2 Write unit tests for the argument and default JSON path
    - Parse args without `--yaml-file`; assert `token_file == "token.json"` (R2.2) and yaml arg default is `None`
    - Parse args with `--yaml-file`/`-y`; assert it is captured
    - _Requirements: 2.2, 3.3_

- [x] 7. Wire the YAML output into `main()` orchestration
  - [x] 7.1 Integrate guard, path resolution, and both writes in `main()`
    - Order: guard PyYAML import (R6.4) → `resolve_yaml_path(token_file, args.yaml_file)`; on `ValueError` print to stderr and `sys.exit(1)` writing neither file (R3.4, R3.5) → existing OAuth flow + `Token_Data` augmentation → `write_token_file` (JSON); on failure print to stderr, leave any pre-existing JSON unchanged, `sys.exit(1)` (R2.5) → `write_yaml_token_file(yaml_path, token_data)`; on failure print a stderr message including the YAML path and cause, `sys.exit(1)`, JSON unchanged (R1.5, R5.1, R5.2) → on success `print` a confirmation naming both the JSON and YAML paths (paths only, no secrets) and exit zero (R5.4)
    - Ensure no `Sensitive_Field` value reaches stdout/stderr on any path (R1.1, R4.3)
    - Keep `write_token_file` (JSON) unchanged so JSON content is independent of YAML args (R2.1, R2.3, R2.4)
    - _Requirements: 1.1, 2.1, 2.5, 5.1, 5.2, 5.4, 6.4_

  - [x] 7.2 Write property test for YAML/JSON equality
    - **Property 2: YAML and JSON parse to equal content**
    - **Validates: Requirements 1.3, 1.4**
    - Tag: `# Feature: store-token-in-yaml-file, Property 2: For any Token_Data, writing it to both a YAML file and a JSON file in the same run and parsing each yields the mapping under the YAML 'token' key equal to the JSON top-level mapping and equal to the original Token_Data`
    - Generate `Token_Data`; write both; assert `yaml.safe_load(y)["token"] == json.load(j) == token_data`; >=100 iterations
    - _Requirements: 1.3, 1.4_

  - [x] 7.3 Write property test for JSON independence from YAML arguments
    - **Property 4: JSON output is independent of YAML arguments**
    - **Validates: Requirements 2.3, 2.4**
    - Tag: `# Feature: store-token-in-yaml-file, Property 4: For any Token_Data, the JSON file content produced with a YAML path argument supplied is byte-for-byte identical to the JSON content produced with no YAML argument`
    - Produce JSON with and without a YAML arg for the same `Token_Data`; assert files are byte-identical; >=100 iterations
    - _Requirements: 2.3, 2.4_

  - [x] 7.4 Write property test for no sensitive value leakage
    - **Property 8: No sensitive value is emitted to stdout or stderr**
    - **Validates: Requirements 4.3, 4.4**
    - Tag: `# Feature: store-token-in-yaml-file, Property 8: For any Token_Data, running the write-and-confirm path emits no Sensitive_Field value to stdout/stderr; and the redaction helper preserves every field name while replacing each Sensitive_Field value with the redaction marker`
    - Capture stdout/stderr via `capsys`; assert no sensitive value substring appears; unit-test the redaction helper directly for name preservation + marker substitution; >=100 iterations
    - _Requirements: 4.3, 4.4_

  - [x] 7.5 Write edge-case tests for JSON write failure and success confirmation
    - JSON write failure (R2.5): monkeypatch to raise during JSON write; assert stderr message and pre-existing JSON bytes unchanged
    - YAML-after-JSON failure (R5.1, R5.2): force YAML write to fail after JSON write; assert stderr includes the YAML path and cause, JSON unchanged, exit non-zero
    - Success confirmation (R5.4): run the success path; assert stdout names both paths and exit is zero
    - JSON format preserved (R2.1, R2.3): extend existing `TestWriteTokenFile` with a 4-space indentation assertion
    - _Requirements: 2.1, 2.3, 2.5, 5.1, 5.2, 5.4_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Re-verify the full suite after the YAML wrapper-key change (tasks 4.1, 4.2, 4.3, 7.2).

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP.
- Each task references specific requirement sub-clauses for traceability.
- Property tests (P1-P8) use Hypothesis with >=100 iterations and are tagged with the required `# Feature: store-token-in-yaml-file, Property {n}: ...` comment.
- Unit/edge-case tests cover all failure modes; config/smoke tests cover the dependency declarations.
- Every requirement R1-R6 and every correctness property P1-P8 is covered by at least one task.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1"] },
    { "id": 1, "tasks": ["1.2", "2.2", "3.2", "3.3", "3.4", "4.1"] },
    { "id": 2, "tasks": ["4.2", "4.3", "4.4", "4.5", "6.1"] },
    { "id": 3, "tasks": ["6.2", "7.1"] },
    { "id": 4, "tasks": ["7.2", "7.3", "7.4", "7.5"] }
  ]
}
```
