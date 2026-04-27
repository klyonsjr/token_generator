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
