import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from app.import_pipeline import HEADERS

FIXTURES = Path(__file__).parent / "fixtures" / "imports"


def run_cli(engine, *, invalid=False, key="cli", extra=()):
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    args = [str(Path(sys.executable).parent / "fairtoy-import"), "--idempotency-key", key]
    for filename in HEADERS:
        directory = "invalid" if invalid and filename == "parts.csv" else "valid"
        args.extend(
            [
                "--" + filename.removesuffix(".csv").replace("_", "-"),
                str(FIXTURES / directory / filename),
            ]
        )
    return subprocess.run(
        [*args, *extra],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        env={**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)},
    )


def test_cli_receipt_and_repeat(import_engine):
    first = run_cli(import_engine)
    assert first.returncode == 0, first.stderr
    receipt = json.loads(first.stdout)
    assert receipt["row_counts"]["inserted"]["parts"] == 2
    second = run_cli(import_engine, invalid=True)
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout) == receipt


def test_cli_failure_and_retry(import_engine):
    result = run_cli(import_engine, invalid=True)
    assert result.returncode == 1
    assert not result.stdout
    assert "parts.csv, row 2" in result.stderr
    assert "No catalog changes were committed." in result.stderr
    with import_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM import_jobs")) == 0
    assert run_cli(import_engine).returncode == 0


def test_cli_requires_arguments_and_has_no_scope(import_engine):
    result = subprocess.run(
        [sys.executable, "-m", "app.import_cli"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "--idempotency-key" in result.stderr
    result = run_cli(import_engine, extra=("--dataset-scope", "unused"))
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
