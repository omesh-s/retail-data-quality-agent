"""Env file merge helpers."""

from __future__ import annotations

from config.env_file import mask_secret, merge_env_file, parse_env_file


def test_merge_preserves_unrelated_keys(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FOO=bar\n# comment\nBAZ=1\n", encoding="utf-8")
    merge_env_file(env, {"RETAIL_DATA_SOURCE": "local_csv"})
    text = env.read_text(encoding="utf-8")
    assert "FOO=bar" in text
    assert "RETAIL_DATA_SOURCE=local_csv" in text
    assert parse_env_file(env)["FOO"] == "bar"


def test_mask_secret():
    assert "…" in mask_secret("sk-abcdefghijklmnop")
