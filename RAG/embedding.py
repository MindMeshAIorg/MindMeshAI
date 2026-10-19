
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
for p in (PROJECT_ROOT, BASE_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

VENV_PACKAGES = PROJECT_ROOT / ".mindmeshenv" / "Lib" / "site-packages"
if VENV_PACKAGES.exists() and str(VENV_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_PACKAGES))

from FlagEmbedding import BGEM3FlagModel



def generate_embeddings(chunks,MODEL_NAME,BATCH_SIZE):
    """Generate BGE-M3 dense and sparse vectors for every chunk."""
    if not chunks:
        return chunks

    model = BGEM3FlagModel(
        MODEL_NAME,
        use_fp16=False,
    )

    texts = [
        chunk["payload"]["actual_text_in_chunk"]
        for chunk in chunks
    ]

    results = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        max_length=8192,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )

    for chunk, dense_vector, sparse_weights in zip(
        chunks,
        results["dense_vecs"],
        results["lexical_weights"],
    ):
        chunk["dense_vector"] = dense_vector.tolist()

        chunk["sparse_vector"] = {
            "indices": [
                int(index) for index in sparse_weights.keys()
            ],
            "values": [
                float(weight) for weight in sparse_weights.values()
            ],
        }

    return chunks