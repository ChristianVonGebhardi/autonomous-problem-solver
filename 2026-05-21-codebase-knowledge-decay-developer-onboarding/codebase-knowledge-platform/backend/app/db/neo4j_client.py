import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver
from typing import Optional, List, Dict, Any

from app.config import settings

logger = structlog.get_logger()


class Neo4jClient:
    def __init__(self):
        self.driver: Optional[AsyncDriver] = None

    async def connect(self):
        self.driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        # Verify connectivity
        try:
            await self.driver.verify_connectivity()
            logger.info("Neo4j connection verified")
        except Exception as e:
            logger.warning("Neo4j not available, some features will be limited", error=str(e))

    async def close(self):
        if self.driver:
            await self.driver.close()

    async def create_indexes(self):
        """Create Neo4j indexes for performance."""
        indexes = [
            "CREATE INDEX repo_name IF NOT EXISTS FOR (r:Repository) ON (r.name)",
            "CREATE INDEX file_path IF NOT EXISTS FOR (f:File) ON (f.path)",
            "CREATE INDEX commit_hash IF NOT EXISTS FOR (c:Commit) ON (c.hash)",
            "CREATE INDEX author_email IF NOT EXISTS FOR (a:Author) ON (a.email)",
            "CREATE INDEX chunk_id IF NOT EXISTS FOR (ch:Chunk) ON (ch.id)",
            "CREATE INDEX pr_number IF NOT EXISTS FOR (p:PullRequest) ON (p.number)",
            "CREATE INDEX concept_name IF NOT EXISTS FOR (co:Concept) ON (co.name)",
        ]
        async with self.driver.session() as session:
            for idx in indexes:
                try:
                    await session.run(idx)
                except Exception as e:
                    logger.debug("Index creation skipped", error=str(e))

    async def run_query(self, cypher: str, params: Dict[str, Any] = None) -> List[Dict]:
        """Execute a Cypher query and return results."""
        if not self.driver:
            return []
        async with self.driver.session() as session:
            result = await session.run(cypher, params or {})
            records = await result.data()
            return records

    async def run_write(self, cypher: str, params: Dict[str, Any] = None):
        """Execute a write Cypher query."""
        if not self.driver:
            return
        async with self.driver.session() as session:
            await session.run(cypher, params or {})

    async def create_repository_node(self, repo_name: str, repo_path: str, metadata: dict):
        cypher = """
        MERGE (r:Repository {name: $name})
        SET r.path = $path,
            r.language = $language,
            r.updated_at = datetime()
        RETURN r
        """
        await self.run_write(cypher, {
            "name": repo_name,
            "path": repo_path,
            "language": metadata.get("language", "unknown"),
        })

    async def create_file_node(self, repo_name: str, file_path: str, metadata: dict):
        cypher = """
        MERGE (r:Repository {name: $repo_name})
        MERGE (f:File {path: $path, repo: $repo_name})
        SET f.extension = $extension,
            f.language = $language,
            f.size_bytes = $size_bytes,
            f.last_modified = $last_modified,
            f.updated_at = datetime()
        MERGE (r)-[:CONTAINS]->(f)
        RETURN f
        """
        await self.run_write(cypher, {
            "repo_name": repo_name,
            "path": file_path,
            "extension": metadata.get("extension", ""),
            "language": metadata.get("language", "unknown"),
            "size_bytes": metadata.get("size_bytes", 0),
            "last_modified": metadata.get("last_modified", ""),
        })

    async def create_commit_node(self, repo_name: str, commit_data: dict):
        cypher = """
        MERGE (c:Commit {hash: $hash})
        SET c.message = $message,
            c.timestamp = $timestamp,
            c.repo = $repo_name
        MERGE (a:Author {email: $author_email})
        SET a.name = $author_name
        MERGE (a)-[:AUTHORED]->(c)
        WITH c
        MATCH (r:Repository {name: $repo_name})
        MERGE (r)-[:HAS_COMMIT]->(c)
        RETURN c
        """
        await self.run_write(cypher, {
            "hash": commit_data["hash"],
            "message": commit_data["message"],
            "timestamp": commit_data["timestamp"],
            "repo_name": repo_name,
            "author_email": commit_data["author_email"],
            "author_name": commit_data["author_name"],
        })

    async def link_commit_to_file(self, commit_hash: str, file_path: str, repo_name: str):
        cypher = """
        MATCH (c:Commit {hash: $hash})
        MERGE (f:File {path: $path, repo: $repo_name})
        MERGE (c)-[:MODIFIES]->(f)
        """
        await self.run_write(cypher, {
            "hash": commit_hash,
            "path": file_path,
            "repo_name": repo_name,
        })

    async def create_chunk_node(self, chunk_id: str, file_path: str, repo_name: str, metadata: dict):
        cypher = """
        MERGE (ch:Chunk {id: $chunk_id})
        SET ch.content_preview = $preview,
            ch.start_line = $start_line,
            ch.end_line = $end_line,
            ch.chunk_type = $chunk_type,
            ch.name = $name
        WITH ch
        MATCH (f:File {path: $file_path, repo: $repo_name})
        MERGE (f)-[:HAS_CHUNK]->(ch)
        RETURN ch
        """
        await self.run_write(cypher, {
            "chunk_id": chunk_id,
            "preview": metadata.get("content", "")[:200],
            "start_line": metadata.get("start_line", 0),
            "end_line": metadata.get("end_line", 0),
            "chunk_type": metadata.get("chunk_type", "code"),
            "name": metadata.get("name", ""),
            "file_path": file_path,
            "repo_name": repo_name,
        })

    async def create_pr_node(self, repo_name: str, pr_data: dict):
        cypher = """
        MERGE (p:PullRequest {number: $number, repo: $repo_name})
        SET p.title = $title,
            p.body = $body,
            p.state = $state,
            p.merged_at = $merged_at,
            p.repo = $repo_name
        MERGE (a:Author {login: $author_login})
        SET a.login = $author_login
        MERGE (a)-[:OPENED]->(p)
        WITH p
        MATCH (r:Repository {name: $repo_name})
        MERGE (r)-[:HAS_PR]->(p)
        RETURN p
        """
        await self.run_write(cypher, {
            "number": pr_data["number"],
            "title": pr_data["title"],
            "body": pr_data.get("body", ""),
            "state": pr_data.get("state", "closed"),
            "merged_at": pr_data.get("merged_at", ""),
            "repo_name": repo_name,
            "author_login": pr_data.get("author", "unknown"),
        })

    async def get_file_history(self, file_path: str, repo_name: str) -> List[Dict]:
        cypher = """
        MATCH (f:File {path: $path, repo: $repo_name})<-[:MODIFIES]-(c:Commit)<-[:AUTHORED]-(a:Author)
        RETURN c.hash AS hash, c.message AS message, c.timestamp AS timestamp,
               a.name AS author_name, a.email AS author_email
        ORDER BY c.timestamp DESC
        LIMIT 20
        """
        return await self.run_query(cypher, {"path": file_path, "repo_name": repo_name})

    async def get_related_files(self, file_path: str, repo_name: str) -> List[Dict]:
        """Find files frequently changed together (co-change coupling)."""
        cypher = """
        MATCH (f:File {path: $path, repo: $repo_name})<-[:MODIFIES]-(c:Commit)-[:MODIFIES]->(other:File)
        WHERE other.path <> $path AND other.repo = $repo_name
        RETURN other.path AS path, count(c) AS co_changes
        ORDER BY co_changes DESC
        LIMIT 10
        """
        return await self.run_query(cypher, {"path": file_path, "repo_name": repo_name})

    async def get_graph_data(self, repo_name: str, limit: int = 100) -> Dict:
        """Get graph visualization data."""
        nodes_cypher = """
        MATCH (n)
        WHERE (n:File OR n:Commit OR n:Author OR n:PullRequest) 
        AND (n.repo = $repo_name OR EXISTS((n)-[:CONTAINS|HAS_COMMIT|HAS_PR]-()))
        RETURN n, labels(n) AS labels
        LIMIT $limit
        """
        edges_cypher = """
        MATCH (a)-[r]->(b)
        WHERE (a:File OR a:Commit OR a:Author OR a:Repository)
        AND (a.repo = $repo_name OR b.repo = $repo_name)
        RETURN a, type(r) AS rel_type, b
        LIMIT $limit
        """
        nodes = await self.run_query(nodes_cypher, {"repo_name": repo_name, "limit": limit})
        edges = await self.run_query(edges_cypher, {"repo_name": repo_name, "limit": limit})
        return {"nodes": nodes, "edges": edges}

    async def search_by_concept(self, concept: str, repo_name: str) -> List[Dict]:
        """Find files/commits related to a concept."""
        cypher = """
        MATCH (r:Repository {name: $repo_name})-[:CONTAINS]->(f:File)
        WHERE toLower(f.path) CONTAINS toLower($concept)
        RETURN f.path AS path, 'file' AS type, 1.0 AS relevance
        UNION
        MATCH (r:Repository {name: $repo_name})-[:HAS_COMMIT]->(c:Commit)
        WHERE toLower(c.message) CONTAINS toLower($concept)
        RETURN c.hash AS path, 'commit' AS type, 0.8 AS relevance
        ORDER BY relevance DESC
        LIMIT 20
        """
        return await self.run_query(cypher, {"concept": concept, "repo_name": repo_name})


neo4j_client = Neo4jClient()