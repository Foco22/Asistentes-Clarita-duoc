import tempfile
from pathlib import Path
from git import Repo
from markitdown import MarkItDown
from src.utils.embeddings import EmbeddingClient
from src.utils.mongodb import MongoDBClient


class PDFIngester:
    def __init__(self, db_name: str = "rag_db", collection_name: str = "chunks"):
        self.embedder = EmbeddingClient()
        self.mongo = MongoDBClient(db_name)
        self.collection = self.mongo.get_collection(collection_name)
        self.converter = MarkItDown()

    def scan_pdfs(self, directory: str) -> list[Path]:
        return list(Path(directory).rglob("*.pdf"))

    def _convert_to_text(self, file_path: Path) -> str:
        result = self.converter.convert(str(file_path))
        return result.text_content

    def _split_text(self, text: str, chunk_size: int = 2200, overlap: int = 200) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start += chunk_size - overlap
        return chunks

    def _already_ingested(self, filename: str) -> bool:
        return self.collection.count_documents({"metadata.filename": filename}) > 0

    def ingest_file(self, file_path: Path):
        if self._already_ingested(file_path.name):
            print(f"Skipping (already ingested): {file_path.name}")
            return

        print(f"Processing: {file_path.name}")
        text = self._convert_to_text(file_path)
        chunks = self._split_text(text)

        documents = []
        for i, chunk in enumerate(chunks):
            embedding = self.embedder.get_embedding(chunk)
            documents.append({
                "chunk_id": i,
                "text": chunk,
                "embedding": embedding,
                "metadata": {
                    "source": str(file_path),
                    "filename": file_path.name,
                    "filetype": file_path.suffix.lower(),
                }
            })

        self.collection.insert_many(documents)
        print(f"  Inserted {len(documents)} chunks.")

    def ingest_directory(self, directory: str):
        pdf_files = self.scan_pdfs(directory)
        print(f"Found {len(pdf_files)} PDF(s) in '{directory}'")
        for file_path in pdf_files:
            self.ingest_file(file_path)
        print("Ingestion complete.")

    def ingest_from_github(self, repo_url: str):
        with tempfile.TemporaryDirectory() as tmp_dir:
            print(f"Cloning {repo_url}...")
            Repo.clone_from(repo_url, tmp_dir)
            self.ingest_directory(tmp_dir)
