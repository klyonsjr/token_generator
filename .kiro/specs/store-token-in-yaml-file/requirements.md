# Requirements Document

## Introduction

The `broker-token` CLI tool authenticates with a broker (Schwab or Tastytrade) via OAuth2 and writes the resulting token data to a JSON file (`token.json` by default). This feature adds a second output: the same token data written to a YAML file, produced **in addition to** the existing JSON file. Both files are written during a single CLI run and must contain the same token field values. The YAML file nests all token fields under a single top-level `token` wrapper key, while the JSON file keeps its existing flat top-level mapping. The existing JSON output and its downstream consumer (`token_refresher`) must continue to work without any change.

## Glossary

- **CLI**: The `broker-token` command-line program whose entry point is `broker_token.cli:main`.
- **Token_Data**: The dictionary of token fields produced by the OAuth2 flow, containing `access_token`, `refresh_token`, `expiration_timestamp`, `refresh_token_expiration_timestamp`, `client_id`, and `client_secret`. Timestamp fields are ISO 8601 strings.
- **JSON_Writer**: The component that serializes Token_Data to a JSON file (currently `write_token_file`).
- **YAML_Writer**: The component that serializes Token_Data to a YAML file (new in this feature).
- **Token_Wrapper_Key**: The single top-level YAML key named `token` whose value is the mapping of Token_Data fields in the YAML_Token_File. This wrapper applies to the YAML_Token_File only; the JSON_Token_File remains a flat top-level mapping with no wrapper key.
- **JSON_Token_File**: The JSON output file (default `token.json`), selected via the `--token-file`/`-o` argument.
- **YAML_Token_File**: The YAML output file produced by this feature.
- **Sensitive_Field**: A Token_Data field whose value is a credential or secret, specifically `client_secret`, `client_id`, `access_token`, and `refresh_token`.

## Requirements

### Requirement 1: Write Token Data to a YAML File

**User Story:** As a broker-token user, I want the token written to a YAML file in addition to the JSON file, so that tools that consume YAML can read the token without a separate conversion step.

#### Acceptance Criteria

1. WHEN the OAuth2 flow completes successfully, THE CLI SHALL write the YAML_Token_File as a mapping with a single top-level Token_Wrapper_Key `token` whose value is a mapping of Token_Data containing the fields access_token, refresh_token, expiration_timestamp, refresh_token_expiration_timestamp, client_id, and client_secret.
2. WHEN the CLI writes the YAML_Token_File, THE YAML_Writer SHALL serialize Token_Data as valid YAML that parses back into a mapping equal to `{"token": Token_Data}`, where the value under the Token_Wrapper_Key is a mapping whose keys and values are equal to the keys and values of Token_Data.
3. THE mapping under the Token_Wrapper_Key in the YAML_Token_File SHALL contain exactly the same set of field names as the top-level mapping of the JSON_Token_File written in the same run, with no additional and no missing fields.
4. WHEN a value in Token_Data is written to both files in the same run, THE CLI SHALL write to the mapping under the Token_Wrapper_Key in the YAML_Token_File a value that, after YAML and JSON parsing, is equal to the value at the corresponding field in the top-level mapping of the JSON_Token_File.
5. IF the YAML_Token_File cannot be written or serialization of Token_Data to YAML fails, THEN THE CLI SHALL leave the JSON_Token_File unchanged, SHALL NOT create a partial or truncated YAML_Token_File, SHALL report an error to standard error that includes the YAML_Token_File path and a description of the failure cause, and SHALL exit with a non-zero status.
6. IF the YAML_Token_File already exists when the OAuth2 flow completes successfully, THEN THE CLI SHALL overwrite the existing YAML_Token_File with the current Token_Data.

### Requirement 2: Preserve Existing JSON Output

**User Story:** As an operator of the downstream `token_refresher`, I want the existing JSON output to remain unchanged, so that my current integration continues to work.

#### Acceptance Criteria

1. WHEN the OAuth2 flow completes successfully, THE CLI SHALL write Token_Data to the JSON_Token_File as UTF-8-encoded JSON indented with 4 spaces, with the Token_Data field names emitted in the same order as before this feature, using the same key/value separators as before this feature, and with the same trailing-newline handling (present or absent) as before this feature.
2. WHERE the user provides no YAML-specific arguments, THE CLI SHALL write the JSON_Token_File to the same default path `token.json` (relative to the current working directory) as before this feature.
3. WHEN the CLI writes the JSON_Token_File, THE JSON_Writer SHALL produce a byte sequence that is byte-for-byte identical to the JSON_Token_File produced before this feature for the same Token_Data.
4. THE JSON_Token_File SHALL be a flat top-level mapping of the Token_Data fields with no Token_Wrapper_Key, so the Token_Wrapper_Key applies to the YAML_Token_File only and the JSON_Token_File byte layout remains unchanged.
5. THE CLI SHALL produce a byte-for-byte identical JSON_Token_File whether or not YAML-specific arguments are supplied for the same Token_Data.
6. IF writing the JSON_Token_File fails, THEN THE CLI SHALL report an error to standard error indicating the JSON_Token_File path and the failure cause, SHALL leave any pre-existing JSON_Token_File byte-for-byte unchanged, and SHALL exit with a non-zero status.

### Requirement 3: Determine the YAML Output Path

**User Story:** As a broker-token user, I want a predictable YAML output path with the ability to override it, so that I can control where the YAML file is written.

#### Acceptance Criteria

1. IF the user provides no YAML path argument AND the JSON_Token_File path contains at least one `.` in its final path segment, THEN THE CLI SHALL derive the YAML_Token_File path by replacing the characters from the last `.` in the final path segment to the end of the path with `.yaml`.
2. IF the user provides no YAML path argument AND the JSON_Token_File path contains no `.` in its final path segment, THEN THE CLI SHALL derive the YAML_Token_File path by appending `.yaml` to the JSON_Token_File path.
3. WHEN the user provides a non-empty YAML path argument, THE CLI SHALL use that user-provided path as the YAML_Token_File path, taking precedence over any derived path.
4. IF the resolved YAML_Token_File path equals the JSON_Token_File path, THEN THE CLI SHALL report an error to standard error indicating that the YAML and JSON output paths conflict, and SHALL exit with a non-zero status without writing either the JSON_Token_File or the YAML_Token_File.
5. IF the user provides a YAML path argument that is empty or contains only whitespace characters, THEN THE CLI SHALL report an error to standard error indicating that the provided YAML path is invalid, and SHALL exit with a non-zero status without writing either file.

### Requirement 4: Protect Sensitive Field Values

**User Story:** As a security-conscious user, I want the YAML file to protect credentials the same way the JSON file does, so that adding YAML output does not weaken the security of my stored token.

#### Acceptance Criteria

1. WHEN the CLI creates the YAML_Token_File, THE CLI SHALL set the file permissions so that the file owner has read and write access and no other user or group has read, write, or execute access.
2. IF the CLI cannot set the required file permissions on the YAML_Token_File, THEN THE CLI SHALL delete the partially written YAML_Token_File and return a non-zero exit status with an error message indicating that the file permissions could not be applied.
3. WHEN the YAML_Writer serializes a Sensitive_Field, THE YAML_Writer SHALL write the field value into the mapping under the Token_Wrapper_Key in the YAML_Token_File only and SHALL NOT write the field value to standard output or standard error.
4. IF an operation writing the YAML_Token_File would otherwise emit a Sensitive_Field value to standard output or standard error, THEN THE CLI SHALL replace the Sensitive_Field value in that output with a fixed redaction marker while preserving the associated field name.

### Requirement 5: Handle YAML Write Failures

**User Story:** As a broker-token user, I want clear feedback when the YAML file cannot be written, so that I know the outcome of the run and am not left with a silently missing file.

#### Acceptance Criteria

1. IF the YAML_Writer fails to write the YAML_Token_File, THEN THE CLI SHALL report an error message to standard error that includes the YAML_Token_File path and a description of the failure cause.
2. IF the YAML_Writer fails to write the YAML_Token_File after the JSON_Token_File has been written successfully, THEN THE CLI SHALL exit with a non-zero status and SHALL leave the JSON_Token_File unchanged.
3. IF a YAML write failure leaves a partial YAML_Token_File, THEN THE CLI SHALL remove the partial YAML_Token_File.
4. WHEN the CLI writes both files successfully, THE CLI SHALL print a confirmation message to standard output that names the JSON_Token_File path and the YAML_Token_File path and SHALL exit with a zero status.

### Requirement 6: Provide the YAML Serialization Dependency

**User Story:** As a developer building or installing broker-token, I want the YAML serialization dependency declared, so that the tool installs and runs without a missing-module error.

#### Acceptance Criteria

1. THE CLI project SHALL declare PyYAML as a project dependency in `pyproject.toml` with a pinned minimum version constraint.
2. THE CLI project SHALL list PyYAML in `requirements.txt` with a version specifier consistent with the one declared in `pyproject.toml`.
3. WHEN the declared dependencies are installed in a clean environment, THE CLI SHALL import the YAML serialization library without raising a module-not-found error.
4. IF the YAML serialization library is not installed when the CLI is invoked, THEN THE CLI SHALL report an error to standard error and SHALL exit with a non-zero status.
