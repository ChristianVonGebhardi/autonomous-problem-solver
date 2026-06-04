import structlog
from pathlib import Path
from typing import List, Dict, Any, Optional

import git
from git import Repo

from app.config import settings
from app.services.chunker import CodeChunker, SKIP_DIRECTORIES, SKIP_EXTENSIONS
from app.services.embedding_service import embed_texts

logger = structlog.get_logger()


class GitIngestionService:
    def __init__(self):
        self.chunker = CodeChunker(
            chunk_size=settings.chunk_size_tokens,
            overlap=settings.chunk_overlap_tokens,
        )

    def open_repo(self, repo_path: str) -> Optional[Repo]:
        try:
            return Repo(repo_path, search_parent_directories=True)
        except Exception as e:
            logger.error("Failed to open git repo", path=repo_path, error=str(e))
            return None

    def get_repo_metadata(self, repo: Repo) -> Dict[str, Any]:
        try:
            remote_url = ""
            if repo.remotes:
                remote_url = repo.remotes[0].url

            head_commit = repo.head.commit

            # Detect primary language by file extension count
            lang_counts: Dict[str, int] = {}
            try:
                for item in repo.tree().traverse():
                    if hasattr(item, "path"):
                        ext = Path(item.path).suffix.lower()
                        if ext:
                            lang_counts[ext] = lang_counts.get(ext, 0) + 1
            except Exception:
                pass

            primary_lang = (
                max(lang_counts, key=lambda k: lang_counts[k]) if lang_counts else "unknown"
            )

            return {
                "remote_url": remote_url,
                "head_commit": head_commit.hexsha,
                "default_branch": (
                    repo.active_branch.name if not repo.head.is_detached else "unknown"
                ),
                "primary_language": primary_lang,
            }
        except Exception as e:
            logger.warning("Could not get full repo metadata", error=str(e))
            return {}

    def iter_commits(self, repo: Repo, max_commits: int = 500) -> List[Dict[str, Any]]:
        """Extract commit history."""
        commits = []
        try:
            for commit in repo.iter_commits(max_count=max_commits):
                changed_files: List[str] = []
                try:
                    if commit.parents:
                        diff = commit.parents[0].diff(commit)
                        changed_files = [d.b_path or d.a_path for d in diff if d.b_path or d.a_path]
                    else:
                        changed_files = [
                            item.path
                            for item in commit.tree.traverse()
                            if hasattr(item, "path")
                        ][:50]
                except Exception:
                    pass

                commits.append(
                    {
                        "hash": commit.hexsha,
                        "short_hash": commit.hexsha[:8],
                        "message": commit.message.strip(),
                        "author_name": commit.author.name or "unknown",
                        "author_email": commit.author.email or "unknown",
                        "timestamp": commit.committed_datetime.isoformat(),
                        "changed_files": changed_files[:20],
                    }
                )
        except Exception as e:
            logger.error("Failed to iterate commits", error=str(e))
        return commits

    def iter_files(self, repo_path: str, repo: Repo) -> List[Dict[str, Any]]:
        """Walk the repo directory tree and return file info."""
        files = []
        repo_path_obj = Path(repo_path)

        try:
            for item in repo.tree().traverse():
                if not hasattr(item, "path"):
                    continue

                file_path = item.path
                path_obj = Path(file_path)

                # Skip unwanted dirs/files
                if any(part in SKIP_DIRECTORIES for part in path_obj.parts):
                    continue
                if path_obj.suffix.lower() in SKIP_EXTENSIONS:
                    continue

                full_path = repo_path_obj / file_path
                if not full_path.exists() or not full_path.is_file():
                    continue

                size = full_path.stat().st_size
                if size > settings.max_file_size_kb * 1024:
                    logger.debug("Skipping large file", path=file_path, size_kb=size // 1024)
                    continue

                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                ext = path_obj.suffix.lower()

                files.append(
                    {
                        "path": file_path,
                        "full_path": str(full_path),
                        "content": content,
                        "extension": ext,
                        "size_bytes": size,
                        "language": self.chunker.get_language(file_path),
                    }
                )
        except Exception as e:
            logger.error("Failed to traverse repo files", error=str(e))

        return files

    async def ingest_repository(
        self,
        repo_path: str,
        repo_name: str,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """
        Full repository ingestion pipeline:
        1. Extract commits → Neo4j graph nodes
        2. Parse files → code chunks
        3. Generate embeddings → Qdrant vector store
        """
        from app.db.neo4j_client import neo4j_client
        from app.db.qdrant_client import qdrant_client

        logger.info("Starting git ingestion", repo=repo_name, path=repo_path)

        repo = self.open_repo(repo_path)
        if not repo:
            return {"success": False, "error": "Cannot open git repository"}

        metadata = self.get_repo_metadata(repo)
        stats: Dict[str, Any] = {
            "commits_processed": 0,
            "files_processed": 0,
            "chunks_created": 0,
            "errors": [],
        }

        # Step 1: Repository node
        await neo4j_client.create_repository_node(repo_name, repo_path, metadata)

        # Step 2: Commits
        if progress_callback:
            await progress_callback(5, "Extracting commits...")

        commits = self.iter_commits(repo, max_commits=200)
        logger.info("Extracted commits", count=len(commits))

        for i, commit in enumerate(commits):
            try:
                await neo4j_client.create_commit_node(repo_name, commit)
                for file_path in commit["changed_files"]:
                    await neo4j_client.link_commit_to_file(
                        commit["hash"], file_path, repo_name
                    )
                stats["commits_processed"] += 1
            except Exception as e:
                stats["errors"].append(f"Commit {commit['hash'][:8]}: {str(e)}")

            if progress_callback and i % 50 == 0:
                pct = 5 + int((i / max(len(commits), 1)) * 25)
                await progress_callback(pct, f"Processing commits ({i}/{len(commits)})...")

        # Step 3: Files and chunks
        if progress_callback:
            await progress_callback(30, "Chunking source files...")

        files = self.iter_files(repo_path, repo)
        logger.info("Found files to process", count=len(files))

        all_chunks = []
        for file_info in files:
            try:
                await neo4j_client.create_file_node(
                    repo_name, file_info["path"], file_info
                )
                chunks = self.chunker.chunk_file(
                    file_info["path"], file_info["content"], repo_name
                )
                all_chunks.extend(chunks)
                stats["files_processed"] += 1

                for chunk in chunks:
                    await neo4j_client.create_chunk_node(
                        chunk.chunk_id,
                        file_info["path"],
                        repo_name,
                        chunk.to_dict(),
                    )
            except Exception as e:
                stats["errors"].append(f"File {file_info['path']}: {str(e)}")

        logger.info("Total chunks created", count=len(all_chunks))

        # Step 4: Embeddings in batches
        if progress_callback:
            await progress_callback(55, "Generating embeddings...")

        batch_size = 64
        total_chunks = len(all_chunks)

        for batch_start in range(0, total_chunks, batch_size):
            batch = all_chunks[batch_start : batch_start + batch_size]
            texts = [
                f"File: {c.file_path}\n{c.chunk_type}: {c.name}\n\n{c.content}"
                for c in batch
            ]

            try:
                embeddings = embed_texts(texts)

                qdrant_points = []
                for chunk, embedding in zip(batch, embeddings):
                    point = chunk.to_dict()
                    point["embedding"] = embedding
                    qdrant_points.append(point)

                await qdrant_client.upsert_chunks(qdrant_points)
                stats["chunks_created"] += len(batch)
            except Exception as e:
                logger.error("Embedding batch failed", error=str(e))
                stats["errors"].append(f"Embedding batch {batch_start}: {str(e)}")

            if progress_callback:
                pct = 55 + int((batch_start / max(total_chunks, 1)) * 40)
                await progress_callback(
                    pct, f"Embedding chunks ({batch_start}/{total_chunks})..."
                )

        if progress_callback:
            await progress_callback(100, "Ingestion complete!")

        logger.info("Git ingestion complete", repo=repo_name, stats=stats)
        return {"success": True, "stats": stats, "metadata": metadata}


git_ingestion_service = GitIngestionService()