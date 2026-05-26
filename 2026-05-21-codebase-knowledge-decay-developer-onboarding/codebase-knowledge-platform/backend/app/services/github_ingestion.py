import structlog
from typing import Optional, Dict, Any, List

from app.config import settings

logger = structlog.get_logger()


class GitHubIngestionService:
    """Ingests PR data and reviews from GitHub."""

    def __init__(self):
        self._github = None

    def _get_client(self):
        if self._github:
            return self._github
        if not settings.github_token:
            logger.warning("No GitHub token configured")
            return None
        try:
            from github import Github
            self._github = Github(settings.github_token)
            return self._github
        except Exception as e:
            logger.error("Failed to create GitHub client", error=str(e))
            return None

    async def clone_repo(self, repo_url: str, local_path: str) -> bool:
        """Clone a GitHub repository to local path."""
        import git
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            auth_url = repo_url
            if settings.github_token and "github.com" in repo_url:
                # Inject token for auth
                auth_url = repo_url.replace(
                    "https://", f"https://{settings.github_token}@"
                )
            await loop.run_in_executor(
                None,
                lambda: git.Repo.clone_from(auth_url, local_path)
            )
            logger.info("Repository cloned", url=repo_url, path=local_path)
            return True
        except Exception as e:
            logger.error("Clone failed", url=repo_url, error=str(e))
            return False

    async def fetch_pull_requests(self, repo_full_name: str, max_prs: int = 100) -> List[Dict[str, Any]]:
        """Fetch PR metadata and review comments."""
        gh = self._get_client()
        if not gh:
            return []

        prs = []
        try:
            repo = gh.get_repo(repo_full_name)
            for pr in repo.get_pulls(state="closed", sort="updated", direction="desc"):
                if len(prs) >= max_prs:
                    break
                
                # Get review comments
                review_comments = []
                try:
                    for review in pr.get_reviews():
                        if review.body:
                            review_comments.append({
                                "author": review.user.login if review.user else "unknown",
                                "body": review.body,
                                "state": review.state,
                            })
                except Exception:
                    pass

                prs.append({
                    "number": pr.number,
                    "title": pr.title,
                    "body": pr.body or "",
                    "state": pr.state,
                    "merged_at": pr.merged_at.isoformat() if pr.merged_at else "",
                    "author": pr.user.login if pr.user else "unknown",
                    "labels": [lbl.name for lbl in pr.labels],
                    "review_comments": review_comments,
                    "changed_files": [f.filename for f in pr.get_files()][:20],
                })
                logger.debug("Fetched PR", number=pr.number)
        except Exception as e:
            logger.error("Failed to fetch PRs", repo=repo_full_name, error=str(e))

        logger.info("Fetched PRs", count=len(prs), repo=repo_full_name)
        return prs

    async def ingest_pull_requests(self, repo_name: str, repo_full_name: str) -> Dict[str, Any]:
        """Ingest PR data into Neo4j and Qdrant."""
        from app.db.neo4j_client import neo4j_client
        from app.db.qdrant_client import qdrant_client
        from app.services.embedding_service import embed_texts

        prs = await self.fetch_pull_requests(repo_full_name)
        
        chunks_to_embed = []
        for pr in prs:
            # Create Neo4j node
            await neo4j_client.create_pr_node(repo_name, pr)
            
            # Create searchable text from PR
            pr_text = f"PR #{pr['number']}: {pr['title']}\n\n{pr['body']}"
            if pr.get("review_comments"):
                for rc in pr["review_comments"]:
                    pr_text += f"\nReview by {rc['author']}: {rc['body']}"
            
            chunks_to_embed.append({
                "chunk_id": f"pr_{repo_name}_{pr['number']}",
                "content": pr_text[:2000],
                "file_path": f"PR #{pr['number']}: {pr['title']}",
                "repo_name": repo_name,
                "chunk_type": "pull_request",
                "name": pr["title"],
                "start_line": 0,
                "end_line": 0,
                "language": "pr",
            })
        
        if chunks_to_embed:
            texts = [c["content"] for c in chunks_to_embed]
            embeddings = embed_texts(texts)
            for chunk, emb in zip(chunks_to_embed, embeddings):
                chunk["embedding"] = emb
            await qdrant_client.upsert_chunks(chunks_to_embed)

        return {"success": True, "prs_ingested": len(prs)}


github_ingestion_service = GitHubIngestionService()