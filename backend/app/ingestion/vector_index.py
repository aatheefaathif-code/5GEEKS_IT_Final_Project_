import argparse
import csv
import gc
import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.rag.constants import COLLECTION_NAME, MODEL_NAME
from app.rag.embeddings import embed_texts, load_embedding_model, mean_pool

DEFAULT_CHUNKS_DIR = Path("data") / "extracted" / "full_chunks_v3"
DEFAULT_OUTPUT_DIR = Path("data") / "index" / "chroma_multilingual_e5_large"
DEFAULT_INVENTORY = Path("data") / "manifests" / "textbook_inventory.csv"
DEFAULT_BATCH_SIZE = 16


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_inventory(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as inventory_file:
        rows = list(csv.DictReader(inventory_file))
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        textbook_id = row.get("textbook_id", "").strip()
        if not textbook_id or textbook_id in result:
            raise ValueError("Inventory contains missing or duplicate textbook IDs.")
        result[textbook_id] = row
    return result


def _embedding_text(chunk: dict[str, Any]) -> str:
    context = [
        f"Grade {chunk['grade']}",
        str(chunk["subject"]),
        str(chunk["medium"]),
    ]
    for field in ("chapter", "lesson", "topic"):
        value = str(chunk.get(field, "unknown")).strip()
        if value and value.casefold() != "unknown":
            context.append(f"{field.title()} {value}")
    return f"passage: {' | '.join(context)}\n{chunk['text'].strip()}"


def _read_chunks(
    chunks_dir: Path,
    inventory_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, str]]:
    report_path = chunks_dir / "chunking_report.json"
    if not report_path.is_file():
        raise FileNotFoundError(f"Chunking report not found: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("pipeline") != "verified_ocr_to_cleaned_lesson_aware_chunks":
        raise ValueError("Chunking report is not from the verified OCR pipeline.")
    if report.get("verification_method") != "user_confirmed_source_pdf_comparison":
        raise ValueError("Chunking report does not record verified OCR provenance.")
    if _sha256(inventory_path) != report.get("inventory_sha256"):
        raise ValueError(
            "Inventory differs from the version used to create these chunks; "
            "regenerate chunks before indexing."
        )

    inventory = _read_inventory(inventory_path)
    chunk_files = sorted(chunks_dir.glob("*.chunks.jsonl"))
    if not chunk_files:
        raise ValueError(f"No chunk JSONL files found in {chunks_dir}.")
    chunks: list[dict[str, Any]] = []
    chunk_ids: set[str] = set()
    seen_books: set[str] = set()
    for chunk_file in chunk_files:
        textbook_id = chunk_file.name.removesuffix(".chunks.jsonl")
        book = inventory.get(textbook_id)
        if book is None:
            raise ValueError(f"Chunk file references unknown textbook: {textbook_id}.")
        seen_books.add(textbook_id)
        with chunk_file.open(encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if chunk.get("textbook_id") != textbook_id:
                    raise ValueError(
                        f"Textbook ID mismatch in {chunk_file}:{line_number}."
                    )
                if chunk.get("page_verification_status") != "verified":
                    raise ValueError(
                        f"Unverified page in {chunk_file}:{line_number}; refusing "
                        "to embed it."
                    )
                if not chunk.get("text", "").strip():
                    raise ValueError(f"Empty chunk in {chunk_file}:{line_number}.")
                if chunk.get("chunk_id") in chunk_ids:
                    raise ValueError(f"Duplicate chunk ID: {chunk.get('chunk_id')}.")
                if chunk.get("grade") != book.get("grade"):
                    raise ValueError(f"Grade mismatch in {chunk_file}:{line_number}.")
                for field in ("subject", "medium"):
                    if chunk.get(field) != book.get(field):
                        raise ValueError(
                            f"{field.title()} mismatch in {chunk_file}:{line_number}."
                        )
                page_number = chunk.get("pdf_page_number")
                if (
                    not isinstance(page_number, int)
                    or page_number < 1
                    or page_number > int(book["page_count"])
                ):
                    raise ValueError(
                        f"Invalid PDF page reference in {chunk_file}:{line_number}."
                    )
                chunk_ids.add(chunk["chunk_id"])
                chunks.append(chunk)

    if len(chunks) != report.get("total_chunks"):
        raise ValueError(
            "Chunk count differs from chunking report: "
            f"read {len(chunks)}, expected {report.get('total_chunks')}."
        )
    if len(seen_books) != report.get("books_selected"):
        raise ValueError(
            "Textbook count differs from chunking report: "
            f"read {len(seen_books)}, expected {report.get('books_selected')}."
        )
    return chunks, report, inventory


def _chromadb_metadata(chunk: dict[str, Any]) -> dict[str, str | int]:
    metadata: dict[str, str | int] = {}
    for field in (
        "textbook_id",
        "grade",
        "subject",
        "medium",
        "textbook_title",
        "edition_or_year",
        "chapter",
        "lesson",
        "topic",
        "page_verification_status",
        "subject_verification_status",
        "source_official_status",
        "source_file",
    ):
        value = chunk.get(field, "unknown")
        metadata[field] = str(value) if value is not None else "unknown"
    metadata["pdf_page_number"] = int(chunk["pdf_page_number"])
    metadata["chunk_id"] = str(chunk["chunk_id"])
    return metadata


def _mean_pool(last_hidden_state: Any, attention_mask: Any) -> Any:
    return mean_pool(last_hidden_state, attention_mask)


def build_vector_index(
    chunks_dir: Path,
    output_dir: Path,
    inventory_path: Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
    chunks_dir = chunks_dir.resolve()
    output_dir = output_dir.resolve()
    inventory_path = inventory_path.resolve()
    if batch_size < 1:
        raise ValueError("batch_size must be positive.")
    if output_dir.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing vector index: {output_dir}"
        )
    if not inventory_path.is_file():
        raise FileNotFoundError(f"Inventory manifest not found: {inventory_path}")

    chunks, _, _ = _read_chunks(chunks_dir, inventory_path)
    chunk_files = sorted(chunks_dir.glob("*.chunks.jsonl"))
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    client: Any | None = None
    try:
        import chromadb
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        tokenizer, model = load_embedding_model(device)
        client = chromadb.PersistentClient(path=str(staging_dir))
        collection = client.create_collection(
            name=COLLECTION_NAME,
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": MODEL_NAME,
                "embedding_normalized": True,
            },
        )
        embedding_dimension: int | None = None
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            embeddings = embed_texts(
                [_embedding_text(chunk) for chunk in batch],
                tokenizer,
                model,
                device,
            ).cpu().numpy()
            if embedding_dimension is None:
                embedding_dimension = int(embeddings.shape[1])
            collection.add(
                ids=[chunk["chunk_id"] for chunk in batch],
                documents=[chunk["text"] for chunk in batch],
                metadatas=[_chromadb_metadata(chunk) for chunk in batch],
                embeddings=embeddings.tolist(),
            )
            print(
                f"Embedded {min(start + len(batch), len(chunks))}/{len(chunks)} chunks",
                flush=True,
            )

        if collection.count() != len(chunks):
            raise RuntimeError(
                f"Vector collection has {collection.count()} records; "
                f"expected {len(chunks)}."
            )
        file_hashes = {path.name: _sha256(path) for path in chunk_files}
        manifest = {
            "created_at": datetime.now(UTC).isoformat(),
            "collection_name": COLLECTION_NAME,
            "embedding_model": MODEL_NAME,
            "embedding_dimension": embedding_dimension,
            "embedding_normalized": True,
            "embedding_input_prefix": "passage: ",
            "device": device,
            "indexed_chunks": len(chunks),
            "textbooks": len(file_hashes),
            "chunks_directory": str(chunks_dir),
            "chunking_report_sha256": _sha256(
                chunks_dir / "chunking_report.json"
            ),
            "inventory_path": str(inventory_path),
            "inventory_sha256": _sha256(inventory_path),
            "chunk_file_sha256": file_hashes,
            "embeddings_created": True,
            "vector_database_created": True,
        }
        (staging_dir / "index_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        del collection
        client.close()
        client = None
        gc.collect()
        staging_dir.replace(output_dir)
        return manifest
    except Exception:
        if client is not None:
            client.close()
            client = None
            gc.collect()
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        raise


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description=(
            "Create a multilingual-e5-large ChromaDB index from verified OCR chunks."
        )
    )
    parser.add_argument(
        "--chunks-dir",
        type=Path,
        default=project_root / DEFAULT_CHUNKS_DIR,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=project_root / DEFAULT_INVENTORY,
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
    )
    args = parser.parse_args()
    result = build_vector_index(
        args.chunks_dir,
        args.output_dir,
        args.inventory,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
