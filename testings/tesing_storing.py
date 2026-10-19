import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "all_output.json"


def store_all_output(chunks):
    """Save all chunk data to JSON without dense or sparse vectors."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    output = []

    for chunk in chunks:
        record = {
            key: value
            for key, value in chunk.items()
            if key not in {"dense_vector", "sparse_vector"}
        }

        output.append(record)

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    print(f"Successfully saved {len(output)} chunks to {OUTPUT_FILE}")