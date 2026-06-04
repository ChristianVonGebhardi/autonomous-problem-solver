import structlog
from fastapi import APIRouter, HTTPException
from typing import Optional

from app.db.neo4j_client import neo4j_client

logger = structlog.get_logger()
router = APIRouter()


@router.get("/{repo_name}/visualization")
async def get_graph_visualization(repo_name: str, limit: int = 100):
    """Get graph data for visualization."""
    try:
        data = await neo4j_client.get_graph_data(repo_name, limit=limit)

        # Transform for frontend consumption
        nodes = []
        edges = []
        seen_nodes = set()

        for record in data.get("nodes", []):
            n = record.get("n", {})
            labels = record.get("labels", [])

            if not n:
                continue

            node_id = (
                n.get("hash")
                or n.get("path")
                or n.get("email")
                or n.get("name")
                or n.get("number")
                or str(n)
            )

            if node_id in seen_nodes:
                continue
            seen_nodes.add(node_id)

            label = labels[0] if labels else "Unknown"
            nodes.append(
                {
                    "id": str(node_id),
                    "label": _get_node_label(n, label),
                    "type": label,
                    "data": {k: str(v)[:100] for k, v in n.items()},
                }
            )

        seen_edges = set()
        for record in data.get("edges", []):
            a = record.get("a", {})
            b = record.get("b", {})
            rel_type = record.get("rel_type", "")

            if not a or not b:
                continue

            source_id = (
                a.get("hash") or a.get("path") or a.get("email") or a.get("name") or str(a)
            )
            target_id = (
                b.get("hash") or b.get("path") or b.get("email") or b.get("name") or str(b)
            )

            edge_key = f"{source_id}:{rel_type}:{target_id}"
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            edges.append(
                {
                    "source": str(source_id),
                    "target": str(target_id),
                    "type": rel_type,
                }
            )

        return {
            "nodes": nodes,
            "edges": edges,
            "repo_name": repo_name,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        }
    except Exception as e:
        logger.error("Graph visualization failed", error=str(e))
        return {
            "nodes": [],
            "edges": [],
            "repo_name": repo_name,
            "stats": {"node_count": 0, "edge_count": 0},
        }


@router.get("/{repo_name}/file-history")
async def get_file_history(repo_name: str, file_path: str):
    """Get commit history for a specific file."""
    try:
        history = await neo4j_client.get_file_history(file_path, repo_name)
        return {"file_path": file_path, "repo_name": repo_name, "history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{repo_name}/related-files")
async def get_related_files(repo_name: str, file_path: str):
    """Get files that are frequently changed together with a given file."""
    try:
        related = await neo4j_client.get_related_files(file_path, repo_name)
        return {"file_path": file_path, "repo_name": repo_name, "related_files": related}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{repo_name}/stats")
async def get_repo_stats(repo_name: str):
    """Get statistics about the repository knowledge graph."""
    # Fix: use proper Cypher with bound variable for authors
    stat_queries = {
        "total_files": (
            "MATCH (f:File {repo: $repo}) RETURN count(f) AS count",
            {"repo": repo_name},
        ),
        "total_commits": (
            "MATCH (c:Commit {repo: $repo}) RETURN count(c) AS count",
            {"repo": repo_name},
        ),
        "total_authors": (
            """
            MATCH (a:Author)-[:AUTHORED]->(c:Commit)
            WHERE c.repo = $repo
            RETURN count(DISTINCT a) AS count
            """,
            {"repo": repo_name},
        ),
        "total_chunks": (
            """
            MATCH (f:File {repo: $repo})-[:HAS_CHUNK]->(ch:Chunk)
            RETURN count(ch) AS count
            """,
            {"repo": repo_name},
        ),
        "total_prs": (
            "MATCH (p:PullRequest {repo: $repo}) RETURN count(p) AS count",
            {"repo": repo_name},
        ),
    }

    stats: dict = {}
    for key, (query, params) in stat_queries.items():
        try:
            result = await neo4j_client.run_query(query, params)
            stats[key] = result[0]["count"] if result else 0
        except Exception as e:
            logger.debug("Stat query failed", key=key, error=str(e))
            stats[key] = 0

    # Top authors
    try:
        top_authors = await neo4j_client.run_query(
            """
            MATCH (a:Author)-[:AUTHORED]->(c:Commit)
            WHERE c.repo = $repo
            RETURN a.name AS name, a.email AS email, count(c) AS commit_count
            ORDER BY commit_count DESC
            LIMIT 5
            """,
            {"repo": repo_name},
        )
        stats["top_authors"] = top_authors
    except Exception as e:
        logger.debug("Top authors query failed", error=str(e))
        stats["top_authors"] = []

    return {"repo_name": repo_name, "stats": stats}


def _get_node_label(node: dict, label: str) -> str:
    if label == "File":
        path = node.get("path", "")
        return path.split("/")[-1] if path else "file"
    elif label == "Commit":
        hash_ = node.get("hash", "")
        msg = node.get("message", "")
        return f"{hash_[:7]}: {msg[:30]}" if hash_ else "commit"
    elif label == "Author":
        return node.get("name") or node.get("email", "author")
    elif label == "PullRequest":
        return f"PR #{node.get('number', '?')}: {node.get('title', '')[:25]}"
    elif label == "Repository":
        return node.get("name", "repo")
    return str(node.get("name", label))