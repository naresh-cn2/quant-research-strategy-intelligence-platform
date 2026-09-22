"""
Tests for qrsip.config — configuration system (spec §28, §4.8 fail-closed).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qrsip.config import (
    ConfigLoader,
    coerce_bool,
    load_yaml_document,
    make_env_example,
    merge_env_overrides,
    resolve_paths,
    sanitize_for_storage,
    validate_required_fields,
)
from qrsip.errors import ConfigurationError


class TestCoerceBool:
    def test_true_boolean(self) -> None:
        assert coerce_bool(True) is True

    def test_false_boolean(self) -> None:
        assert coerce_bool(False) is False

    def test_string_true(self) -> None:
        assert coerce_bool("true") is True
        assert coerce_bool("TRUE") is True
        assert coerce_bool("Yes") is True
        assert coerce_bool("1") is True

    def test_string_false(self) -> None:
        assert coerce_bool("false") is False
        assert coerce_bool("FALSE") is False
        assert coerce_bool("No") is False
        assert coerce_bool("0") is False
        assert coerce_bool("") is False

    def test_integer_true(self) -> None:
        assert coerce_bool(1) is True
        assert coerce_bool(0) is False

    def test_invalid_coercion_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot coerce"):
            coerce_bool("maybe")


class TestLoadYamlDocument:
    def test_loads_valid_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / "cfg.yaml"
        p.write_text("a: 1\nb: hello\n", encoding="utf-8")
        result = load_yaml_document(p)
        assert result == {"a": 1, "b": "hello"}

    def test_rejects_missing_file(self, tmp_path: Path) -> None:
        p = tmp_path / "missing.yaml"
        with pytest.raises(ConfigurationError, match="does not exist"):
            load_yaml_document(p)

    def test_rejects_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.yaml"
        p.write_text("", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="empty"):
            load_yaml_document(p)

    def test_rejects_non_mapping(self, tmp_path: Path) -> None:
        p = tmp_path / "list.yaml"
        p.write_text("- 1\n- 2\n", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="must contain a mapping"):
            load_yaml_document(p)

    def test_rejects_invalid_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("::: not yaml :::", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="not valid YAML"):
            load_yaml_document(p)

    def test_rejects_unreadable_file(self, tmp_path: Path) -> None:
        p = tmp_path / "noaccess.yaml"
        p.write_text("a: 1", encoding="utf-8")
        p.chmod(0o000)
        try:
            with pytest.raises(ConfigurationError, match="cannot read"):
                load_yaml_document(p)
        finally:
            p.chmod(0o644)


class TestResolvePaths:
    def test_resolves_relative_paths(self, tmp_path: Path) -> None:
        mapping = {"data_path": "data/raw", "output_dir": "reports"}
        result = resolve_paths(mapping, base=tmp_path)
        assert result["data_path"] == (tmp_path / "data" / "raw").resolve()
        assert result["output_dir"] == (tmp_path / "reports").resolve()

    def test_does_not_touch_unknown_keys(self, tmp_path: Path) -> None:
        mapping = {"x": "data/raw", "y": 42}
        result = resolve_paths(mapping, base=tmp_path, keys=("z",))
        assert result["x"] == "data/raw"
        assert result["y"] == 42

    def test_mutates_original_mapping(self, tmp_path: Path) -> None:
        mapping = {"data_path": "data"}
        original_id = id(mapping)
        resolve_paths(mapping, base=tmp_path)
        assert id(mapping) == original_id
        assert mapping["data_path"] == (tmp_path / "data").resolve()


class TestValidateRequiredFields:
    def test_passes_when_all_present(self) -> None:
        mapping = {"a": 1, "b": 2, "c": 3}
        validate_required_fields(mapping, ("a", "b"))

    def test_fails_when_missing(self) -> None:
        mapping = {"a": 1}
        with pytest.raises(ConfigurationError, match="missing required field"):
            validate_required_fields(mapping, ("a", "b"))

    def test_fails_when_empty_required_list(self) -> None:
        mapping = {}
        with pytest.raises(ConfigurationError, match="required fields must be non-empty"):
            validate_required_fields(mapping, ())


class TestSanitizeForStorage:
    def test_path_becomes_string(self, tmp_path: Path) -> None:
        result = sanitize_for_storage(tmp_path / "x")
        assert isinstance(result, str)

    def test_dict_recursive(self) -> None:
        result = sanitize_for_storage({"a": Path("/x"), "b": [Path("/y")]})
        assert result["a"] == "/x"
        assert result["b"] == ["/y"]

    def test_bytes_becomes_hex(self) -> None:
        result = sanitize_for_storage(b"hello")
        assert result == "68656c6c6f"


class TestConfigLoader:
    def test_load_resolves_paths(self, tmp_path: Path) -> None:
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text("data_path: data/raw\n", encoding="utf-8")
        loader = ConfigLoader(base_dir=tmp_path)
        result = loader.load(cfg, resolve_path_keys=("data_path",))
        assert result["data_path"] == (tmp_path / "data" / "raw").resolve()

    def test_load_rejects_missing(self, tmp_path: Path) -> None:
        loader = ConfigLoader()
        with pytest.raises(ConfigurationError):
            loader.load(tmp_path / "missing.yaml")

    def test_validate_passes(self, tmp_path: Path) -> None:
        loader = ConfigLoader()
        loader.validate({"a": 1}, required=("a",))

    def test_validate_fails(self, tmp_path: Path) -> None:
        loader = ConfigLoader()
        with pytest.raises(ConfigurationError):
            loader.validate({"a": 1}, required=("a", "b"))

    def test_dump_json_serializable(self, tmp_path: Path) -> None:
        loader = ConfigLoader()
        mapping = {"path": tmp_path / "x", "items": [tmp_path / "y"]}
        result = loader.dump_json_serializable(mapping)
        assert isinstance(result["path"], str)
        assert isinstance(result["items"][0], str)


class TestMergeEnvOverrides:
    def test_overrides_simple_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QRSIP_LOG_LEVEL", "DEBUG")
        mapping = {"log_level": "INFO"}
        result = merge_env_overrides(mapping)
        assert result["log_level"] == "DEBUG"

    def test_does_not_touch_non_prefixed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTHER_VAR", "x")
        mapping = {"log_level": "INFO"}
        result = merge_env_overrides(mapping)
        assert result["log_level"] == "INFO"

    def test_returns_new_mapping(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QRSIP_LOG_LEVEL", "DEBUG")
        mapping = {"log_level": "INFO"}
        result = merge_env_overrides(mapping)
        assert result is not mapping


class TestMakeEnvExample:
    def test_emits_documentation_structure(self, tmp_path: Path) -> None:
        text = make_env_example(out_path=tmp_path / ".env.example")
        assert "QRSIP_" in text
        assert "#" in text

    def test_writes_file_when_path_given(self, tmp_path: Path) -> None:
        out = tmp_path / ".env.example"
        make_env_example(out_path=out)
        assert out.is_file()
