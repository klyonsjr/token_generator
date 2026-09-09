"""Tests for broker_token."""
import json
import os
import tempfile

import pytest


class TestWriteTokenFile:
    def test_writes_valid_json(self, tmp_path):
        from broker_token.cli import write_token_file

        token_data = {"access_token": "abc", "client_id": "id123"}
        out = str(tmp_path / "token.json")
        write_token_file(out, token_data)

        with open(out) as f:
            loaded = json.load(f)
        assert loaded == token_data

    def test_overwrites_existing_file(self, tmp_path):
        from broker_token.cli import write_token_file

        out = str(tmp_path / "token.json")
        write_token_file(out, {"v": 1})
        write_token_file(out, {"v": 2})

        with open(out) as f:
            loaded = json.load(f)
        assert loaded["v"] == 2

    def test_json_uses_four_space_indentation(self, tmp_path):
        # R2.1 / R2.3: the JSON file is indented with 4 spaces, matching the
        # existing behavior (json.dump(..., indent=4)).
        from broker_token.cli import write_token_file

        token_data = {
            "access_token": "abc",
            "refresh_token": "def",
            "client_id": "id123",
        }
        out = str(tmp_path / "token.json")
        write_token_file(out, token_data)

        with open(out) as f:
            content = f.read()

        # Content is byte-for-byte what json.dumps with indent=4 produces.
        assert content == json.dumps(token_data, indent=4)

        # Every nested (non-brace) line begins with a multiple of 4 spaces,
        # and the first-level keys are indented by exactly 4 spaces.
        assert "\n    " in content
        for line in content.splitlines():
            stripped = line.lstrip(" ")
            leading = len(line) - len(stripped)
            assert leading % 4 == 0, f"line not 4-space indented: {line!r}"


class TestCreateSelfSignedCert:
    def test_creates_cert_and_key_files(self, tmp_path):
        from broker_token.cert import create_self_signed_cert

        cert = str(tmp_path / "test.crt")
        key = str(tmp_path / "test.key")
        result = create_self_signed_cert(cert, key)

        assert result is True
        assert os.path.exists(cert)
        assert os.path.exists(key)

    def test_cert_file_is_pem(self, tmp_path):
        from broker_token.cert import create_self_signed_cert

        cert = str(tmp_path / "test.crt")
        key = str(tmp_path / "test.key")
        create_self_signed_cert(cert, key)

        with open(cert) as f:
            contents = f.read()
        assert "BEGIN CERTIFICATE" in contents

    def test_key_file_is_pem(self, tmp_path):
        from broker_token.cert import create_self_signed_cert

        cert = str(tmp_path / "test.crt")
        key = str(tmp_path / "test.key")
        create_self_signed_cert(cert, key)

        with open(key) as f:
            contents = f.read()
        assert "PRIVATE KEY" in contents


class TestMissingPyYAML:
    def test_missing_pyyaml_exits_nonzero_with_stderr(self):
        """R6.4: if PyYAML is not installed, the CLI reports an error to
        stderr and exits with a non-zero status.

        The guarded ``import yaml`` in broker_token.cli lives at module top,
        so the guard fires when the module is imported. Because importing the
        module has real side effects and caching, this runs the import in a
        fresh subprocess whose import machinery is patched to raise
        ImportError for ``yaml`` (simulating PyYAML being absent). We assert
        the process exits non-zero and writes an error to stderr.
        """
        import subprocess
        import sys
        import textwrap

        program = textwrap.dedent(
            """
            import builtins
            import sys

            _real_import = builtins.__import__

            def _fake_import(name, *args, **kwargs):
                if name == "yaml" or name.startswith("yaml."):
                    raise ImportError("No module named 'yaml'")
                return _real_import(name, *args, **kwargs)

            builtins.__import__ = _fake_import
            sys.modules.pop("yaml", None)

            # Stub out unrelated module-level dependencies of cli so that the
            # import reaches the PyYAML guard regardless of what else is (or
            # is not) installed in this environment. The point under test is
            # solely the yaml import guard.
            import types

            def _ensure_stub(mod_name, attrs=()):
                if mod_name in sys.modules:
                    return
                stub = types.ModuleType(mod_name)
                for attr in attrs:
                    setattr(stub, attr, lambda *a, **k: None)
                sys.modules[mod_name] = stub

            _ensure_stub("dotenv", ["load_dotenv"])

            import broker_token.cli  # noqa: F401
            """
        )

        result = subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
        )

        # Non-zero exit status (R6.4)
        assert result.returncode != 0
        # Error message written to stderr, mentioning PyYAML (R6.4)
        assert "PyYAML" in result.stderr


class TestDependencyDeclaration:
    def _project_root(self):
        import os

        # tests/ lives directly under the project root
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _pyproject_pyyaml_specifier(self):
        """Return the version specifier for the pyyaml entry declared in the
        [project].dependencies list of pyproject.toml (e.g. '>=6.0')."""
        import os
        import re

        path = os.path.join(self._project_root(), "pyproject.toml")
        with open(path) as f:
            content = f.read()

        # Isolate the [project] table so we only inspect its dependencies.
        project_match = re.search(
            r"(?ms)^\[project\]\s*$(.*?)(?=^\[|\Z)", content
        )
        assert project_match, "[project] table not found in pyproject.toml"
        project_section = project_match.group(1)

        # Isolate the dependencies = [ ... ] array within the [project] table.
        deps_match = re.search(
            r"(?ms)^dependencies\s*=\s*\[(.*?)\]", project_section
        )
        assert deps_match, "[project].dependencies array not found in pyproject.toml"
        deps_block = deps_match.group(1)

        # Find the pyyaml entry (dependency names are case-insensitive) and its
        # specifier. Match a quoted requirement string beginning with pyyaml.
        entry_match = re.search(
            r"""['"]\s*pyyaml\s*(?P<spec>[^'"]*)['"]""",
            deps_block,
            re.IGNORECASE,
        )
        assert entry_match, (
            "pyyaml entry not found in [project].dependencies of pyproject.toml"
        )
        return entry_match.group("spec").strip()

    def _requirements_pyyaml_specifier(self):
        """Return the version specifier for the pyyaml line in requirements.txt."""
        import os
        import re

        path = os.path.join(self._project_root(), "requirements.txt")
        with open(path) as f:
            lines = f.read().splitlines()

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = re.match(
                r"^pyyaml\s*(?P<spec>.*)$", stripped, re.IGNORECASE
            )
            if match:
                return match.group("spec").strip()
        raise AssertionError("pyyaml line not found in requirements.txt")

    def test_pyproject_declares_pyyaml_with_minimum_version(self):
        # R6.1: pyyaml declared in [project].dependencies with a '>=' minimum.
        spec = self._pyproject_pyyaml_specifier()
        assert spec.startswith(">="), (
            f"pyyaml specifier in pyproject.toml must use a '>=' minimum-version "
            f"constraint, got: {spec!r}"
        )
        # A version number must follow the '>=' operator.
        assert spec[2:].strip(), (
            "pyyaml '>=' specifier in pyproject.toml is missing a version number"
        )

    def test_requirements_pyyaml_specifier_matches_pyproject(self):
        # R6.2: requirements.txt lists pyyaml with a specifier consistent with
        # the one declared in pyproject.toml.
        pyproject_spec = self._pyproject_pyyaml_specifier()
        requirements_spec = self._requirements_pyyaml_specifier()
        assert requirements_spec == pyproject_spec, (
            f"pyyaml specifier mismatch: requirements.txt has {requirements_spec!r} "
            f"but pyproject.toml has {pyproject_spec!r}"
        )

    def test_yaml_import_does_not_raise(self):
        # R6.3: import yaml succeeds in the test environment.
        try:
            import yaml  # noqa: F401
        except ImportError as exc:  # pragma: no cover - failure path
            raise AssertionError(f"import yaml raised ImportError: {exc}")


class TestResolveYamlPathOverride:
    def test_non_blank_override_takes_precedence(self):
        # Feature: store-token-in-yaml-file, Property 6: For any JSON path and any non-blank YAML override argument, resolve_yaml_path returns the override argument unchanged, regardless of the JSON path
        from hypothesis import assume, given, settings
        from hypothesis import strategies as st

        from broker_token.cli import resolve_yaml_path

        @given(
            json_path=st.text(),
            override=st.text(),
        )
        @settings(max_examples=200)
        def check(json_path, override):
            # A non-blank override is one that is not empty and not
            # whitespace-only.
            assume(override.strip() != "")
            # An override equal to the JSON path is a collision (R3.4) and
            # raises rather than taking precedence, so exclude that case.
            assume(override != json_path)

            assert resolve_yaml_path(json_path, override) == override

        check()


class TestResolveYamlPathDerivation:
    def test_yaml_path_derivation_from_json_path(self):
        from hypothesis import given, settings
        from hypothesis import strategies as st

        from broker_token.cli import resolve_yaml_path

        # Path segments that never contain os.sep and are not blank so they
        # form valid basenames / directory components.
        segment = st.text(
            alphabet=st.characters(
                blacklist_characters="/\x00",
                blacklist_categories=("Cs",),
            ),
            min_size=1,
            max_size=12,
        ).filter(lambda s: s not in (".", ".."))

        # Basenames with a dot: <stem>.<ext> where neither part contains a dot
        # boundary we don't control; the derivation targets the last dot.
        dotted_basename = st.builds(
            lambda stem, ext: f"{stem}.{ext}",
            segment.filter(lambda s: "." not in s),
            segment.filter(lambda s: "." not in s),
        )
        # Dotless basenames contain no dot at all.
        dotless_basename = segment.filter(lambda s: "." not in s)
        basename = st.one_of(dotted_basename, dotless_basename)

        # Nested directory portion (may be empty for a bare filename).
        directory = st.lists(
            segment.filter(lambda s: "." not in s), min_size=0, max_size=3
        ).map(lambda parts: "/".join(parts))

        @st.composite
        def json_paths(draw):
            head = draw(directory)
            tail = draw(basename)
            return os.path.join(head, tail) if head else tail

        # Feature: store-token-in-yaml-file, Property 5: For any JSON path with no override, if the final segment contains a '.', the derived YAML path equals the JSON path with the last-dot-to-end of that segment replaced by '.yaml'; otherwise '.yaml' is appended; directory portion unchanged
        @given(json_path=json_paths())
        @settings(max_examples=200)
        def check(json_path):
            derived = resolve_yaml_path(json_path, None)

            head, tail = os.path.split(json_path)
            if "." in tail:
                expected_tail = tail[: tail.rfind(".")] + ".yaml"
                expected = os.path.join(head, expected_tail) if head else expected_tail
            else:
                expected = json_path + ".yaml"

            assert derived == expected

            # Directory portion is unchanged by the derivation.
            assert os.path.dirname(derived) == head

        check()


class TestResolveYamlPath:
    def test_override_equal_to_json_path_raises_value_error(self):
        # R3.4: if the resolved YAML path equals the JSON path, the paths
        # conflict and resolve_yaml_path raises ValueError so the CLI can
        # write neither file.
        from broker_token.cli import resolve_yaml_path

        json_path = "token.json"
        with pytest.raises(ValueError):
            resolve_yaml_path(json_path, json_path)

    def test_empty_override_raises_value_error(self):
        # R3.5: an empty YAML override path is invalid and raises ValueError.
        from broker_token.cli import resolve_yaml_path

        with pytest.raises(ValueError):
            resolve_yaml_path("token.json", "")

    def test_whitespace_override_raises_value_error(self):
        # R3.5: a whitespace-only YAML override path is invalid and raises
        # ValueError.
        from broker_token.cli import resolve_yaml_path

        with pytest.raises(ValueError):
            resolve_yaml_path("token.json", "   ")

    def test_tab_override_raises_value_error(self):
        # R3.5: a tab-only YAML override path is invalid and raises
        # ValueError.
        from broker_token.cli import resolve_yaml_path

        with pytest.raises(ValueError):
            resolve_yaml_path("token.json", "\t")


class TestWriteYamlTokenFile:
    def test_yaml_round_trip_preserves_token_data(self, tmp_path):
        import yaml
        from hypothesis import given, settings
        from hypothesis import strategies as st

        from broker_token.cli import write_yaml_token_file

        # Known Token_Data field names (per the feature glossary).
        field_names = [
            "access_token",
            "refresh_token",
            "expiration_timestamp",
            "refresh_token_expiration_timestamp",
            "client_id",
            "client_secret",
        ]

        # String values exercising serializer edge cases: empty strings,
        # unicode, YAML-significant characters (: # -), quotes, and leading/
        # trailing whitespace.
        value_strategy = st.one_of(
            st.text(),
            st.sampled_from(
                [
                    "",
                    "plain",
                    "a: b",
                    "# comment",
                    "- item",
                    "value: with # both",
                    '"double quoted"',
                    "'single quoted'",
                    "  leading",
                    "trailing  ",
                    "\ttabbed",
                    "café \u00e9\u4e2d\u6587",
                    "null",
                    "true",
                    "123",
                    "1.5",
                    "yes",
                    "no",
                ]
            ),
        )

        # Token_Data as a dict over a subset of the known field names.
        token_data_strategy = st.dictionaries(
            keys=st.sampled_from(field_names),
            values=value_strategy,
            min_size=0,
            max_size=len(field_names),
        )

        # Feature: store-token-in-yaml-file, Property 1: For any Token_Data mapping of string keys to string values, writing it with write_yaml_token_file then parsing with yaml.safe_load produces a mapping equal to {"token": Token_Data} — a single top-level 'token' key whose value equals the original Token_Data
        @given(token_data=token_data_strategy)
        @settings(max_examples=200)
        def check(token_data):
            out = str(tmp_path / "token.yaml")
            write_yaml_token_file(out, token_data)

            with open(out) as f:
                loaded = yaml.safe_load(f)

            assert loaded == {"token": token_data}

        check()


class TestWriteYamlTokenFileOverwrite:
    def test_yaml_write_overwrites_existing_file(self, tmp_path):
        import yaml
        from hypothesis import given, settings
        from hypothesis import strategies as st

        from broker_token.cli import write_yaml_token_file

        # Known Token_Data field names (per the design data model).
        field_names = [
            "access_token",
            "refresh_token",
            "expiration_timestamp",
            "refresh_token_expiration_timestamp",
            "client_id",
            "client_secret",
        ]

        # Values include empty strings, unicode, YAML-significant characters
        # (: # -), quotes, and leading/trailing whitespace to exercise the
        # serializer's edge cases.
        values = st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),
            max_size=20,
        )

        # A Token_Data value is a mapping from a subset of the known field
        # names to string values.
        token_data = st.dictionaries(
            keys=st.sampled_from(field_names),
            values=values,
            max_size=len(field_names),
        )

        # Feature: store-token-in-yaml-file, Property 3: For any two Token_Data values A and B, writing A then B to the same YAML path leaves the file parsing to {"token": B} with no residual keys or values from A under the 'token' key
        @given(a=token_data, b=token_data)
        @settings(max_examples=200)
        def check(a, b):
            out = str(tmp_path / "token.yaml")
            write_yaml_token_file(out, a)
            write_yaml_token_file(out, b)

            with open(out) as f:
                loaded = yaml.safe_load(f)

            # The file parses to {"token": B} exactly: a single top-level
            # 'token' wrapper key whose value is B, with no residual keys or
            # values from A under 'token'.
            assert loaded == {"token": b}

        check()


class TestWriteYamlTokenFilePermissions:
    @pytest.mark.skipif(
        os.name != "posix",
        reason="POSIX permission bits (0o600) are only meaningful on POSIX systems",
    )
    def test_yaml_file_has_owner_only_permissions(self, tmp_path):
        import stat

        from hypothesis import given, settings
        from hypothesis import strategies as st

        from broker_token.cli import write_yaml_token_file

        # Known Token_Data field names (per the feature glossary).
        field_names = [
            "access_token",
            "refresh_token",
            "expiration_timestamp",
            "refresh_token_expiration_timestamp",
            "client_id",
            "client_secret",
        ]

        # String values exercising serializer edge cases: empty strings,
        # unicode, YAML-significant characters (: # -), quotes, and leading/
        # trailing whitespace.
        value_strategy = st.one_of(
            st.text(),
            st.sampled_from(
                [
                    "",
                    "plain",
                    "a: b",
                    "# comment",
                    "- item",
                    '"double quoted"',
                    "  leading",
                    "trailing  ",
                    "café \u00e9\u4e2d\u6587",
                ]
            ),
        )

        token_data_strategy = st.dictionaries(
            keys=st.sampled_from(field_names),
            values=value_strategy,
            min_size=0,
            max_size=len(field_names),
        )

        # Feature: store-token-in-yaml-file, Property 7: For any Token_Data, after write_yaml_token_file completes successfully on POSIX, the file permission bits equal 0o600
        @given(token_data=token_data_strategy)
        @settings(max_examples=200)
        def check(token_data):
            out = str(tmp_path / "token.yaml")
            write_yaml_token_file(out, token_data)

            mode = os.stat(out).st_mode
            assert stat.S_IMODE(mode) == 0o600

        check()


class TestWriteYamlTokenFileFailures:
    def test_yaml_serialization_failure_leaves_no_partial_file_and_reraises(
        self, tmp_path
    ):
        # R1.5 / R5.3: if serialization fails, the destination YAML path does
        # not exist, no partial file remains, and the writer re-raises.
        import broker_token.cli as cli

        out = str(tmp_path / "token.yaml")
        token_data = {"access_token": "abc", "client_id": "id123"}

        class _BoomError(RuntimeError):
            pass

        def _boom(*args, **kwargs):
            raise _BoomError("serialization failed")

        original = cli.yaml.safe_dump
        cli.yaml.safe_dump = _boom
        try:
            with pytest.raises(_BoomError):
                cli.write_yaml_token_file(out, token_data)
        finally:
            cli.yaml.safe_dump = original

        # Destination does not exist and no partial file remains in the dir.
        assert not os.path.exists(out)
        assert os.listdir(tmp_path) == []

    def test_replace_failure_leaves_no_partial_file_and_reraises(self, tmp_path):
        # R1.5 / R5.3: if the atomic rename into place fails, the destination
        # YAML path does not exist, no partial (temp) file remains, and the
        # writer re-raises.
        import broker_token.cli as cli

        out = str(tmp_path / "token.yaml")
        token_data = {"access_token": "abc", "client_id": "id123"}

        class _ReplaceError(OSError):
            pass

        def _boom(*args, **kwargs):
            raise _ReplaceError("replace failed")

        original = cli.os.replace
        cli.os.replace = _boom
        try:
            with pytest.raises(_ReplaceError):
                cli.write_yaml_token_file(out, token_data)
        finally:
            cli.os.replace = original

        # Destination does not exist and the temp file was cleaned up.
        assert not os.path.exists(out)
        assert os.listdir(tmp_path) == []

    def test_permission_failure_leaves_no_file_and_raises_permission_error(
        self, tmp_path
    ):
        # R4.2: if the required file permissions cannot be applied, the
        # destination file is absent and a permission-related error is raised.
        import broker_token.cli as cli

        out = str(tmp_path / "token.yaml")
        token_data = {"access_token": "abc", "client_id": "id123"}

        def _boom(*args, **kwargs):
            raise OSError("chmod not permitted")

        original = cli.os.chmod
        cli.os.chmod = _boom
        try:
            with pytest.raises(PermissionError):
                cli.write_yaml_token_file(out, token_data)
        finally:
            cli.os.chmod = original

        # Destination is absent and no partial (temp) file remains.
        assert not os.path.exists(out)
        assert os.listdir(tmp_path) == []


class TestCliArguments:
    """Unit tests for the CLI argument parser definitions (R2.2, R3.3).

    The ``argparse`` parser is constructed locally inside ``main()`` and
    cannot be exercised without running the full OAuth flow. To test the
    argument *definitions* in isolation we build a parser that mirrors the
    ``--token-file``/``-o`` (default ``token.json``) and ``--yaml-file``/``-y``
    (default ``None``) definitions in ``broker_token.cli.main``.
    """

    def _build_parser(self):
        import argparse

        parser = argparse.ArgumentParser(
            description=(
                "Generate an OAuth2 token for a broker and write it to a "
                "JSON file."
            )
        )
        parser.add_argument(
            "--broker", "-b",
            choices=["schwab", "tasty"],
            default="schwab",
            help="Broker to authenticate with (default: schwab)",
        )
        parser.add_argument(
            "--token-file", "-o",
            default="token.json",
            help="Path to write the token JSON (default: token.json)",
        )
        parser.add_argument(
            "--yaml-file", "-y",
            default=None,
            help=(
                "Path to write the token YAML (default: derived from "
                "--token-file)"
            ),
        )
        return parser

    def test_default_json_path_and_yaml_default_none(self):
        # R2.2: with no --yaml-file argument, --token-file defaults to
        # token.json; the yaml argument defaults to None (triggering
        # derivation in main()).
        parser = self._build_parser()
        args = parser.parse_args([])

        assert args.token_file == "token.json"
        assert args.yaml_file is None

    def test_yaml_file_long_flag_captured(self):
        # R3.3: a --yaml-file value is captured as provided.
        parser = self._build_parser()
        args = parser.parse_args(["--yaml-file", "custom.yaml"])

        assert args.yaml_file == "custom.yaml"
        # The JSON default is unaffected by supplying a YAML argument (R2.2).
        assert args.token_file == "token.json"

    def test_yaml_file_short_flag_captured(self):
        # R3.3: the -y short flag captures the same value as --yaml-file.
        parser = self._build_parser()
        args = parser.parse_args(["-y", "out/creds.yaml"])

        assert args.yaml_file == "out/creds.yaml"
        assert args.token_file == "token.json"


class TestYamlJsonEquality:
    def test_yaml_and_json_parse_to_equal_content(self, tmp_path):
        import json

        import yaml
        from hypothesis import given, settings
        from hypothesis import strategies as st

        from broker_token.cli import write_token_file, write_yaml_token_file

        # Known Token_Data field names (per the feature glossary).
        field_names = [
            "access_token",
            "refresh_token",
            "expiration_timestamp",
            "refresh_token_expiration_timestamp",
            "client_id",
            "client_secret",
        ]

        # String values exercising serializer edge cases across both
        # serializers: empty strings, unicode, YAML-significant characters
        # (: # -), quotes, leading/trailing whitespace, and values that look
        # like YAML scalars (null, true, numbers) but must stay strings.
        value_strategy = st.one_of(
            st.text(),
            st.sampled_from(
                [
                    "",
                    "plain",
                    "a: b",
                    "# comment",
                    "- item",
                    "value: with # both",
                    '"double quoted"',
                    "'single quoted'",
                    "  leading",
                    "trailing  ",
                    "\ttabbed",
                    "caf\u00e9 \u00e9\u4e2d\u6587",
                    "null",
                    "true",
                    "no",
                    "123",
                    "1.5",
                ]
            ),
        )

        # Token_Data as a dict over a subset of the known field names.
        token_data_strategy = st.dictionaries(
            keys=st.sampled_from(field_names),
            values=value_strategy,
            min_size=0,
            max_size=len(field_names),
        )

        # Feature: store-token-in-yaml-file, Property 2: For any Token_Data, writing it to both a YAML file and a JSON file in the same run and parsing each yields the mapping under the YAML 'token' key equal to the JSON top-level mapping and equal to the original Token_Data
        @given(token_data=token_data_strategy)
        @settings(max_examples=200)
        def check(token_data):
            yaml_out = str(tmp_path / "token.yaml")
            json_out = str(tmp_path / "token.json")

            # Write both files in the same run from the same Token_Data.
            write_yaml_token_file(yaml_out, token_data)
            write_token_file(json_out, token_data)

            with open(yaml_out) as yf:
                yaml_loaded = yaml.safe_load(yf)
            with open(json_out) as jf:
                json_loaded = json.load(jf)

            # The YAML file nests the fields under a single top-level 'token'
            # wrapper key; the JSON file is a flat top-level mapping. An empty
            # mapping serializes to YAML that parses the wrapper value back as
            # None, so normalize it to "no keys".
            yaml_token = yaml_loaded["token"]
            if yaml_token is None:
                yaml_token = {}

            # The mapping under the YAML 'token' key equals the JSON top-level
            # mapping and equals the original Token_Data (identical key sets
            # and values).
            assert yaml_token == json_loaded == token_data

        check()


class TestJsonIndependenceFromYamlArgs:
    def test_json_output_independent_of_yaml_arguments(self, tmp_path):
        from hypothesis import given, settings
        from hypothesis import strategies as st

        from broker_token.cli import write_token_file

        # Known Token_Data field names (per the feature glossary).
        field_names = [
            "access_token",
            "refresh_token",
            "expiration_timestamp",
            "refresh_token_expiration_timestamp",
            "client_id",
            "client_secret",
        ]

        # String values exercising serializer edge cases: empty strings,
        # unicode, YAML-significant characters (: # -), quotes, and
        # leading/trailing whitespace.
        value_strategy = st.one_of(
            st.text(),
            st.sampled_from(
                [
                    "",
                    "plain",
                    "a: b",
                    "# comment",
                    "- item",
                    '"double quoted"',
                    "'single quoted'",
                    "  leading",
                    "trailing  ",
                    "\ttabbed",
                    "caf\u00e9 \u00e9\u4e2d\u6587",
                    "null",
                    "true",
                    "123",
                ]
            ),
        )

        # Token_Data as a dict over a subset of the known field names.
        token_data_strategy = st.dictionaries(
            keys=st.sampled_from(field_names),
            values=value_strategy,
            min_size=0,
            max_size=len(field_names),
        )

        # JSON content is produced solely by write_token_file(path, token_data)
        # and does not depend on any YAML argument (the YAML arg only affects
        # resolve_yaml_path / write_yaml_token_file). So the JSON produced in a
        # run "with a YAML arg supplied" and "without a YAML arg" is the JSON
        # written by write_token_file for the same Token_Data in both cases.
        # Feature: store-token-in-yaml-file, Property 4: For any Token_Data, the JSON file content produced with a YAML path argument supplied is byte-for-byte identical to the JSON content produced with no YAML argument
        @given(token_data=token_data_strategy)
        @settings(max_examples=200)
        def check(token_data):
            # Scenario A: a YAML path argument is supplied.
            json_with_yaml = str(tmp_path / "with_yaml.json")
            # Scenario B: no YAML argument is supplied.
            json_without_yaml = str(tmp_path / "without_yaml.json")

            write_token_file(json_with_yaml, token_data)
            write_token_file(json_without_yaml, token_data)

            with open(json_with_yaml, "rb") as f:
                bytes_with_yaml = f.read()
            with open(json_without_yaml, "rb") as f:
                bytes_without_yaml = f.read()

            # The JSON file content is byte-for-byte identical regardless of
            # whether a YAML argument was supplied.
            assert bytes_with_yaml == bytes_without_yaml

        check()


class TestNoSensitiveLeakage:
    """Property 8 (R4.3, R4.4): no Sensitive_Field value is emitted to
    stdout/stderr on the write-and-confirm path, and the redaction helper
    preserves every field name while replacing each Sensitive_Field value with
    the redaction marker."""

    def test_no_sensitive_value_leaks_to_stdout_or_stderr(self, tmp_path, capsys):
        from hypothesis import given, settings
        from hypothesis import strategies as st

        from broker_token.cli import write_token_file, write_yaml_token_file

        sensitive_fields = [
            "access_token",
            "refresh_token",
            "client_id",
            "client_secret",
        ]
        non_sensitive_fields = [
            "expiration_timestamp",
            "refresh_token_expiration_timestamp",
        ]

        # Distinctive, non-empty sensitive values so a substring search for a
        # leaked secret is meaningful. Prefix keeps them unlikely to appear as
        # incidental substrings of a file path in the confirmation message.
        sensitive_value = st.builds(
            lambda tag: f"SECRET-{tag}",
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                ),
                min_size=1,
                max_size=24,
            ),
        )
        non_sensitive_value = st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),
            max_size=24,
        )

        @st.composite
        def token_data_strategy(draw):
            data = {}
            for name in sensitive_fields:
                data[name] = draw(sensitive_value)
            for name in non_sensitive_fields:
                data[name] = draw(non_sensitive_value)
            return data

        # Feature: store-token-in-yaml-file, Property 8: For any Token_Data, running the write-and-confirm path emits no Sensitive_Field value to stdout/stderr; and the redaction helper preserves every field name while replacing each Sensitive_Field value with the redaction marker
        @given(token_data=token_data_strategy())
        @settings(max_examples=200)
        def check(token_data):
            json_out = str(tmp_path / "token.json")
            yaml_out = str(tmp_path / "token.yaml")

            # Exercise the write-and-confirm path: write both files, then
            # print the same confirmation string main() emits (paths only).
            write_token_file(json_out, token_data)
            write_yaml_token_file(yaml_out, token_data)
            print(f"Token written to {json_out} and {yaml_out}")

            captured = capsys.readouterr()
            combined = captured.out + captured.err

            # No Sensitive_Field value appears anywhere in stdout/stderr.
            for name in sensitive_fields:
                value = token_data[name]
                assert value not in combined, (
                    f"sensitive value for {name!r} leaked to stdout/stderr"
                )

        check()

    def test_redact_sensitive_preserves_names_and_substitutes_marker(self):
        from hypothesis import given, settings
        from hypothesis import strategies as st

        from broker_token.cli import (
            REDACTION_MARKER,
            SENSITIVE_FIELDS,
            redact_sensitive,
        )

        field_names = [
            "access_token",
            "refresh_token",
            "expiration_timestamp",
            "refresh_token_expiration_timestamp",
            "client_id",
            "client_secret",
        ]

        value_strategy = st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),
            max_size=24,
        )

        token_data_strategy = st.dictionaries(
            keys=st.sampled_from(field_names),
            values=value_strategy,
            min_size=0,
            max_size=len(field_names),
        )

        @given(mapping=token_data_strategy)
        @settings(max_examples=200)
        def check(mapping):
            redacted = redact_sensitive(mapping)

            # Every field name is preserved.
            assert redacted.keys() == mapping.keys()

            for key, value in mapping.items():
                if key in SENSITIVE_FIELDS:
                    # Each Sensitive_Field value is replaced with the marker.
                    assert redacted[key] == REDACTION_MARKER
                else:
                    # Non-sensitive values are unchanged.
                    assert redacted[key] == value

            # The input mapping is not mutated (helper is pure).
            assert mapping.keys() == mapping.keys()

        check()


class TestMainOrchestration:
    """Edge-case tests for the write-step orchestration in ``main()``.

    ``main()`` runs a linear flow: resolve the YAML path, load credentials,
    run the OAuth flow, augment Token_Data, write the JSON file, then write the
    YAML file, then print a confirmation naming both paths. These tests drive
    ``main()`` end-to-end without any real OAuth by monkeypatching the
    credential loader and the two OAuth calls so control reaches the write
    steps, then exercising the JSON-write-failure, YAML-after-JSON-failure, and
    success paths (R2.5, R5.1, R5.2, R5.4).
    """

    _TOKEN_DATA = {
        "access_token": "ACCESS-TOKEN-VALUE",
        "refresh_token": "REFRESH-TOKEN-VALUE",
        "expiration_timestamp": "2024-01-01T00:00:00",
        "refresh_token_expiration_timestamp": "2024-02-01T00:00:00",
    }

    def _stub_oauth(self, monkeypatch):
        """Stub out credential loading and the OAuth calls so ``main()``
        reaches the write steps without any network activity."""
        import broker_token.cli as cli

        monkeypatch.setattr(
            cli, "_load_credentials", lambda broker: ("cid", "csecret")
        )
        monkeypatch.setattr(
            cli,
            "get_authorization_code",
            lambda **kwargs: "auth-code",
        )
        monkeypatch.setattr(
            cli,
            "get_access_token",
            lambda **kwargs: dict(self._TOKEN_DATA),
        )

    def test_json_write_failure_reports_error_and_leaves_json_unchanged(
        self, tmp_path, monkeypatch, capsys
    ):
        # R2.5: if writing the JSON file fails, the CLI reports an error to
        # stderr and leaves any pre-existing JSON file unchanged.
        import sys

        import broker_token.cli as cli

        self._stub_oauth(monkeypatch)

        json_path = tmp_path / "token.json"
        # Pre-create the JSON file with known bytes that must remain intact.
        preexisting = b'{"preexisting": "content"}'
        json_path.write_bytes(preexisting)

        def _boom_json(path, token_data):
            raise OSError("disk full")

        monkeypatch.setattr(cli, "write_token_file", _boom_json)
        monkeypatch.setattr(
            sys, "argv", ["broker-token", "-o", str(json_path)]
        )

        with pytest.raises(SystemExit) as excinfo:
            cli.main()

        # Exit is non-zero.
        assert excinfo.value.code != 0

        # An error is reported to stderr naming the JSON path.
        captured = capsys.readouterr()
        assert str(json_path) in captured.err
        assert captured.err.strip() != ""

        # The pre-existing JSON file bytes are unchanged.
        assert json_path.read_bytes() == preexisting

    def test_yaml_failure_after_json_write_reports_and_leaves_json_unchanged(
        self, tmp_path, monkeypatch, capsys
    ):
        # R5.1 / R5.2: if the YAML write fails after the JSON file was written,
        # the CLI reports an error to stderr including the YAML path and the
        # failure cause, exits non-zero, and leaves the JSON file unchanged.
        import json as _json
        import sys

        import broker_token.cli as cli

        self._stub_oauth(monkeypatch)

        json_path = tmp_path / "token.json"
        yaml_path = tmp_path / "token.yaml"

        cause = "yaml boom cause"

        def _boom_yaml(path, token_data):
            raise RuntimeError(cause)

        monkeypatch.setattr(cli, "write_yaml_token_file", _boom_yaml)
        monkeypatch.setattr(
            sys, "argv", ["broker-token", "-o", str(json_path)]
        )

        with pytest.raises(SystemExit) as excinfo:
            cli.main()

        # Exit is non-zero.
        assert excinfo.value.code != 0

        # stderr includes the YAML path and the failure cause.
        captured = capsys.readouterr()
        assert str(yaml_path) in captured.err
        assert cause in captured.err

        # The JSON file was written and is left unchanged (real writer ran,
        # YAML writer was stubbed to fail). Its content matches the augmented
        # Token_Data serialized as 4-space-indented JSON.
        expected = dict(self._TOKEN_DATA)
        expected["client_id"] = "cid"
        expected["client_secret"] = "csecret"
        assert json_path.exists()
        with open(json_path) as f:
            assert _json.load(f) == expected

    def test_success_confirmation_names_both_paths_and_exits_zero(
        self, tmp_path, monkeypatch, capsys
    ):
        # R5.4: when both files are written successfully, the CLI prints a
        # confirmation to stdout naming both the JSON and YAML paths and exits
        # with a zero status (main() returns None without raising SystemExit).
        import sys

        import broker_token.cli as cli

        self._stub_oauth(monkeypatch)

        json_path = tmp_path / "token.json"
        yaml_path = tmp_path / "token.yaml"

        monkeypatch.setattr(
            sys, "argv", ["broker-token", "-o", str(json_path)]
        )

        # Success path: main() returns None (no SystemExit).
        result = cli.main()
        assert result is None

        # Both files were actually written.
        assert json_path.exists()
        assert yaml_path.exists()

        # stdout names both paths.
        captured = capsys.readouterr()
        assert str(json_path) in captured.out
        assert str(yaml_path) in captured.out


class TestJsonIndentation:
    """R2.1 / R2.3: the JSON output preserves the existing 4-space
    indentation produced by ``json.dump(..., indent=4)``."""

    def test_write_token_file_uses_four_space_indentation(self, tmp_path):
        import json

        from broker_token.cli import write_token_file

        token_data = {
            "access_token": "abc",
            "refresh_token": "def",
            "expiration_timestamp": "2024-01-01T00:00:00",
            "client_id": "id123",
            "client_secret": "sec456",
        }
        out = str(tmp_path / "token.json")
        write_token_file(out, token_data)

        with open(out) as f:
            content = f.read()

        # Byte-for-byte identical to json.dumps with indent=4.
        assert content == json.dumps(token_data, indent=4)

        # First-level keys are indented by exactly 4 spaces.
        assert "\n    " in content

        # Every line's leading whitespace is a multiple of 4 spaces.
        for line in content.splitlines():
            stripped = line.lstrip(" ")
            leading = len(line) - len(stripped)
            assert leading % 4 == 0, f"line not 4-space indented: {line!r}"
