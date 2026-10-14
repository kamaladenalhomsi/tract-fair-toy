"""Local CSV import command."""

import argparse
import json
import sys
from pathlib import Path

from psycopg import Error as PsycopgError
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.import_pipeline import HEADERS, ImportValidationError, import_files


def main(argv=None):
    parser = argparse.ArgumentParser(description="Atomically import six FairToy CSV files")
    parser.add_argument("--idempotency-key", required=True)
    for filename in HEADERS:
        parser.add_argument(
            "--" + filename.removesuffix(".csv").replace("_", "-"), type=Path, required=True
        )
    args = parser.parse_args(argv)
    files = {filename: getattr(args, filename.removesuffix(".csv")) for filename in HEADERS}
    engine = create_engine(get_settings().database_url)
    try:
        receipt = import_files(engine, files, args.idempotency_key)
    except (ImportValidationError, PsycopgError, SQLAlchemyError) as exc:
        print(f"{exc}\nNo catalog changes were committed.", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
