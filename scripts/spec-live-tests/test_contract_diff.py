#!/usr/bin/env python3
"""
Unit tests for contract_diff.py — runs the YAML readers and diff engine
against in-memory fixtures so they pass in CI without needing a real
waves-platform release.
"""
import json
import sys
import tempfile
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import contract_diff as cd  # noqa: E402


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _yaml(text: str) -> dict:
    import yaml
    return yaml.safe_load(text)


# ----------------------------------------------------------------------------
# YAML readers
# ----------------------------------------------------------------------------

def test_openapi_op_params():
    doc = _yaml("""
paths:
  /foo:
    post:
      operationId: doFoo
      parameters:
        - name: a
          in: query
        - name: b
          in: query
        - name: c
          in: header
""")
    assert cd.read_openapi_op_params(doc, "doFoo") == {"a", "b"}
    assert cd.read_openapi_op_params(doc, "nope") == set()


def test_openapi_op_body_inline_schema():
    doc = _yaml("""
paths:
  /foo:
    post:
      operationId: doFoo
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                x: { type: string }
                y: { type: integer }
""")
    assert cd.read_openapi_op_body(doc, "doFoo") == {"x", "y"}


def test_openapi_op_body_ref_resolution():
    doc = _yaml("""
paths:
  /foo:
    post:
      operationId: doFoo
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/FooReq'
components:
  schemas:
    FooReq:
      type: object
      properties:
        a: { type: string }
        b: { type: number }
""")
    assert cd.read_openapi_op_body(doc, "doFoo") == {"a", "b"}


def test_asyncapi_server_query():
    doc = _yaml("""
servers:
  production:
    bindings:
      ws:
        query:
          properties:
            language: { type: string }
            sample_rate: { type: integer }
""")
    assert cd.read_asyncapi_server_query(doc, "production") == {"language", "sample_rate"}
    assert cd.read_asyncapi_server_query(doc, "missing") == set()


def test_asyncapi_message_payload():
    doc = _yaml("""
channels:
  myChan:
    messages:
      req.message:
        payload:
          properties:
            text: { type: string }
            voice_id: { type: string }
""")
    assert cd.read_asyncapi_message_payload(doc, "myChan", "req.message") == {"text", "voice_id"}


# ----------------------------------------------------------------------------
# Manifest loader + platform_param_set
# ----------------------------------------------------------------------------

def test_load_manifests_and_platform_param_set():
    fixtures = THIS_DIR / "contract_diff_fixtures"
    manifests = cd.load_manifests(fixtures)
    assert "stt" in manifests
    plat = cd.platform_param_set(manifests["stt"], "fixtureRestQuerySchema", frozenset())
    assert plat == {"language", "punctuate", "keywords"}


def test_platform_param_set_respects_ignore():
    fixtures = THIS_DIR / "contract_diff_fixtures"
    manifests = cd.load_manifests(fixtures)
    plat = cd.platform_param_set(manifests["stt"], "fixtureRestQuerySchema", frozenset(["keywords"]))
    assert plat == {"language", "punctuate"}


def test_platform_is_passthrough():
    m = {
        "schemas": {
            "passSchema": {"additionalProperties": "passthrough", "properties": {}},
            "stripSchema": {"additionalProperties": "strip", "properties": {}},
        }
    }
    assert cd.platform_is_passthrough(m, "passSchema") is True
    assert cd.platform_is_passthrough(m, "stripSchema") is False
    assert cd.platform_is_passthrough(m, "missing") is False


# ----------------------------------------------------------------------------
# Diff engine
# ----------------------------------------------------------------------------

def test_diff_mapping_finds_missing_and_extras(tmp_path: Path):
    # Build a synthetic docs spec for the fixture manifest's schema.
    docs_file = tmp_path / "openapi.yaml"
    docs_file.write_text("""
paths:
  /foo:
    post:
      operationId: fooOp
      parameters:
        - name: language
          in: query
        - name: extra_in_docs_only
          in: query
""")
    mapping = cd.Mapping(
        surface="stt",
        platform_schema="fixtureRestQuerySchema",
        docs_file="openapi.yaml",
        selector_kind="openapi-op-params",
        selector=("fooOp",),
    )
    manifest = json.loads((THIS_DIR / "contract_diff_fixtures/stt.json").read_text())
    report = cd.diff_mapping(mapping, manifest, tmp_path)
    assert report.docs_present is True
    assert report.platform_present is True
    assert set(report.missing_in_docs) == {"punctuate", "keywords"}
    assert set(report.extra_in_docs) == {"extra_in_docs_only"}


def test_diff_mapping_passthrough_suppresses_extras(tmp_path: Path):
    # Schema with passthrough — docs extras should NOT be flagged.
    manifest = {
        "schemas": {
            "passSchema": {
                "additionalProperties": "passthrough",
                "properties": {"model": {"kind": "string"}},
            }
        }
    }
    docs_file = tmp_path / "openapi.yaml"
    docs_file.write_text("""
paths:
  /foo:
    post:
      operationId: fooOp
      parameters:
        - name: model
          in: query
        - name: temperature
          in: query
        - name: top_p
          in: query
""")
    mapping = cd.Mapping(
        surface="x",
        platform_schema="passSchema",
        docs_file="openapi.yaml",
        selector_kind="openapi-op-params",
        selector=("fooOp",),
    )
    report = cd.diff_mapping(mapping, manifest, tmp_path)
    assert report.missing_in_docs == []
    # Passthrough → extras suppressed
    assert report.extra_in_docs == []
    assert report.is_clean()


def test_diff_mapping_handles_missing_docs_file(tmp_path: Path):
    mapping = cd.Mapping(
        surface="x",
        platform_schema="fixtureRestQuerySchema",
        docs_file="does-not-exist.yaml",
        selector_kind="openapi-op-params",
        selector=("nope",),
    )
    manifest = json.loads((THIS_DIR / "contract_diff_fixtures/stt.json").read_text())
    report = cd.diff_mapping(mapping, manifest, tmp_path)
    assert report.docs_present is False


# ----------------------------------------------------------------------------
# Report rendering
# ----------------------------------------------------------------------------

def test_render_markdown_skips_clean_pairs():
    manifests = {"x": {"platform_commit": "abc", "surface": "x"}}
    reports = [
        cd.MappingReport(
            mapping=cd.Mapping(surface="x", platform_schema="s", docs_file="f.yaml",
                              selector_kind="openapi-op-params", selector=("op",)),
            missing_in_docs=[], extra_in_docs=[], docs_present=True, platform_present=True,
        )
    ]
    md = cd.render_markdown(reports, [], manifests)
    # Marker is rendered as "✅ In sync" (capital I) — case-insensitive check.
    assert "✅" in md
    assert "sync" in md.lower()


def test_render_markdown_shows_deletions():
    deletions = [cd.DeletionReport(
        docs_file="x.yaml", selector_kind="openapi-op-params",
        selector=("op",), deleted=["foo", "bar"],
    )]
    md = cd.render_markdown([], deletions, {})
    assert "🚨 Deletions" in md
    assert "foo" in md and "bar" in md


# ----------------------------------------------------------------------------
# Tiny test runner — keeps the script standalone (no pytest dep required).
# ----------------------------------------------------------------------------

def _run():
    failures = 0
    passed = 0
    tests = [(name, obj) for name, obj in globals().items() if name.startswith("test_") and callable(obj)]
    for name, fn in tests:
        # Inject tmp_path if needed.
        try:
            import inspect
            sig = inspect.signature(fn)
            if "tmp_path" in sig.parameters:
                with tempfile.TemporaryDirectory() as td:
                    fn(Path(td))
            else:
                fn()
            print(f"  ✓ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {name}\n      {e}")
            failures += 1
        except Exception as e:
            print(f"  ✗ {name}\n      {type(e).__name__}: {e}")
            failures += 1
    print(f"\n{passed} passed, {failures} failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run())
