import re
import structlog
from pathlib import Path
from typing import List, Dict, Any, Optional
import hashlib

logger = structlog.get_logger()

# Language detection by extension
LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".sql": "sql",
    ".sh": "bash",
    ".dockerfile": "dockerfile",
}

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".pdf", ".zip", ".tar", ".gz", ".lock",
    ".min.js", ".min.css", ".map",
}

SKIP_DIRECTORIES = {
    "node_modules", ".git", "__pycache__", ".pytest_cache",
    "dist", "build", ".next", "vendor", "venv", ".venv",
    "coverage", ".nyc_output",
}


class CodeChunk:
    def __init__(
        self,
        content: str,
        file_path: str,
        repo_name: str,
        start_line: int,
        end_line: int,
        chunk_type: str = "code",
        name: str = "",
        language: str = "",
    ):
        self.content = content
        self.file_path = file_path
        self.repo_name = repo_name
        self.start_line = start_line
        self.end_line = end_line
        self.chunk_type = chunk_type
        self.name = name
        self.language = language
        self.chunk_id = self._compute_id()

    def _compute_id(self) -> str:
        key = f"{self.repo_name}:{self.file_path}:{self.start_line}:{self.end_line}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "file_path": self.file_path,
            "repo_name": self.repo_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "chunk_type": self.chunk_type,
            "name": self.name,
            "language": self.language,
        }


class CodeChunker:
    """
    Simple but effective code chunker that uses regex-based
    structural parsing to identify functions, classes, and logical blocks.
    Falls back to sliding window for unsupported languages.
    """

    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def get_language(self, file_path: str) -> str:
        path = Path(file_path)
        ext = path.suffix.lower()
        return LANGUAGE_MAP.get(ext, "unknown")

    def should_skip(self, file_path: str) -> bool:
        path = Path(file_path)
        # Skip by extension
        if path.suffix.lower() in SKIP_EXTENSIONS:
            return True
        # Skip by directory
        parts = set(path.parts)
        if parts & SKIP_DIRECTORIES:
            return True
        return False

    def chunk_file(self, file_path: str, content: str, repo_name: str) -> List[CodeChunk]:
        """Chunk a file into meaningful segments."""
        if not content or not content.strip():
            return []

        language = self.get_language(file_path)

        if language == "python":
            chunks = self._chunk_python(content, file_path, repo_name, language)
        elif language in ("javascript", "typescript"):
            chunks = self._chunk_js_ts(content, file_path, repo_name, language)
        elif language == "markdown":
            chunks = self._chunk_markdown(content, file_path, repo_name, language)
        else:
            chunks = self._chunk_generic(content, file_path, repo_name, language)

        return chunks

    def _chunk_python(self, content: str, file_path: str, repo_name: str, language: str) -> List[CodeChunk]:
        chunks = []
        lines = content.split("\n")
        
        # Patterns for Python structural elements
        func_pattern = re.compile(r'^(\s*)(async\s+)?def\s+(\w+)\s*\(')
        class_pattern = re.compile(r'^(\s*)class\s+(\w+)\s*[:(]')

        current_block_start = 0
        current_block_name = ""
        current_block_type = "module"
        current_indent = 0

        i = 0
        block_lines = []
        
        while i < len(lines):
            line = lines[i]
            
            cls_match = class_pattern.match(line)
            func_match = func_pattern.match(line)
            
            if cls_match or func_match:
                # Save previous block
                if block_lines:
                    chunk_content = "\n".join(block_lines)
                    if len(chunk_content.strip()) > 20:
                        chunks.append(CodeChunk(
                            content=chunk_content,
                            file_path=file_path,
                            repo_name=repo_name,
                            start_line=current_block_start + 1,
                            end_line=i,
                            chunk_type=current_block_type,
                            name=current_block_name,
                            language=language,
                        ))
                
                if cls_match:
                    current_block_name = cls_match.group(2)
                    current_block_type = "class"
                    current_indent = len(cls_match.group(1))
                else:
                    current_block_name = func_match.group(3)
                    current_block_type = "function"
                    current_indent = len(func_match.group(1))
                
                current_block_start = i
                block_lines = [line]
            else:
                block_lines.append(line)
            
            i += 1
        
        # Final block
        if block_lines:
            chunk_content = "\n".join(block_lines)
            if len(chunk_content.strip()) > 20:
                chunks.append(CodeChunk(
                    content=chunk_content,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=current_block_start + 1,
                    end_line=len(lines),
                    chunk_type=current_block_type,
                    name=current_block_name,
                    language=language,
                ))
        
        # If no chunks found, fall back to generic
        if not chunks:
            return self._chunk_generic(content, file_path, repo_name, language)
        
        # Split large chunks
        return self._split_large_chunks(chunks)

    def _chunk_js_ts(self, content: str, file_path: str, repo_name: str, language: str) -> List[CodeChunk]:
        chunks = []
        lines = content.split("\n")

        # Patterns for JS/TS
        func_patterns = [
            re.compile(r'^(\s*)(export\s+)?(default\s+)?(async\s+)?function\s+(\w+)'),
            re.compile(r'^(\s*)(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s+)?\('),
            re.compile(r'^(\s*)(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s+)?function'),
        ]
        class_pattern = re.compile(r'^(\s*)(export\s+)?(default\s+)?class\s+(\w+)')

        block_start = 0
        block_name = ""
        block_type = "module"
        block_lines = []

        for i, line in enumerate(lines):
            matched = False
            
            cls_match = class_pattern.match(line)
            if cls_match:
                if block_lines:
                    chunk_content = "\n".join(block_lines)
                    if len(chunk_content.strip()) > 20:
                        chunks.append(CodeChunk(
                            content=chunk_content,
                            file_path=file_path,
                            repo_name=repo_name,
                            start_line=block_start + 1,
                            end_line=i,
                            chunk_type=block_type,
                            name=block_name,
                            language=language,
                        ))
                block_name = cls_match.group(4)
                block_type = "class"
                block_start = i
                block_lines = [line]
                matched = True
            
            if not matched:
                for pattern in func_patterns:
                    m = pattern.match(line)
                    if m:
                        if block_lines:
                            chunk_content = "\n".join(block_lines)
                            if len(chunk_content.strip()) > 20:
                                chunks.append(CodeChunk(
                                    content=chunk_content,
                                    file_path=file_path,
                                    repo_name=repo_name,
                                    start_line=block_start + 1,
                                    end_line=i,
                                    chunk_type=block_type,
                                    name=block_name,
                                    language=language,
                                ))
                        groups = m.groups()
                        block_name = groups[-1] if groups[-1] else ""
                        block_type = "function"
                        block_start = i
                        block_lines = [line]
                        matched = True
                        break
            
            if not matched:
                block_lines.append(line)

        if block_lines:
            chunk_content = "\n".join(block_lines)
            if len(chunk_content.strip()) > 20:
                chunks.append(CodeChunk(
                    content=chunk_content,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=block_start + 1,
                    end_line=len(lines),
                    chunk_type=block_type,
                    name=block_name,
                    language=language,
                ))

        if not chunks:
            return self._chunk_generic(content, file_path, repo_name, language)

        return self._split_large_chunks(chunks)

    def _chunk_markdown(self, content: str, file_path: str, repo_name: str, language: str) -> List[CodeChunk]:
        chunks = []
        lines = content.split("\n")
        heading_pattern = re.compile(r'^(#{1,3})\s+(.+)')

        current_heading = "Introduction"
        current_start = 0
        current_lines = []

        for i, line in enumerate(lines):
            m = heading_pattern.match(line)
            if m:
                if current_lines:
                    chunk_content = "\n".join(current_lines)
                    if len(chunk_content.strip()) > 10:
                        chunks.append(CodeChunk(
                            content=chunk_content,
                            file_path=file_path,
                            repo_name=repo_name,
                            start_line=current_start + 1,
                            end_line=i,
                            chunk_type="documentation",
                            name=current_heading,
                            language=language,
                        ))
                current_heading = m.group(2)
                current_start = i
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            chunk_content = "\n".join(current_lines)
            if len(chunk_content.strip()) > 10:
                chunks.append(CodeChunk(
                    content=chunk_content,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=current_start + 1,
                    end_line=len(lines),
                    chunk_type="documentation",
                    name=current_heading,
                    language=language,
                ))

        if not chunks:
            return self._chunk_generic(content, file_path, repo_name, language)
        return chunks

    def _chunk_generic(self, content: str, file_path: str, repo_name: str, language: str) -> List[CodeChunk]:
        """Sliding window chunking for unsupported languages."""
        lines = content.split("\n")
        chunks = []
        
        step = max(1, self.chunk_size - self.overlap)
        i = 0
        chunk_num = 0
        
        while i < len(lines):
            end = min(i + self.chunk_size, len(lines))
            chunk_lines = lines[i:end]
            chunk_content = "\n".join(chunk_lines)
            
            if len(chunk_content.strip()) > 10:
                chunks.append(CodeChunk(
                    content=chunk_content,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=i + 1,
                    end_line=end,
                    chunk_type="code",
                    name=f"chunk_{chunk_num}",
                    language=language,
                ))
            
            i += step
            chunk_num += 1
        
        return chunks

    def _split_large_chunks(self, chunks: List[CodeChunk]) -> List[CodeChunk]:
        """Split chunks that are too large into smaller ones."""
        result = []
        for chunk in chunks:
            lines = chunk.content.split("\n")
            if len(lines) <= self.chunk_size * 2:
                result.append(chunk)
            else:
                # Split into sub-chunks
                step = self.chunk_size
                for i in range(0, len(lines), step):
                    sub_lines = lines[i:i + step]
                    sub_content = "\n".join(sub_lines)
                    if sub_content.strip():
                        result.append(CodeChunk(
                            content=sub_content,
                            file_path=chunk.file_path,
                            repo_name=chunk.repo_name,
                            start_line=chunk.start_line + i,
                            end_line=chunk.start_line + i + len(sub_lines),
                            chunk_type=chunk.chunk_type,
                            name=f"{chunk.name}_{i // step}",
                            language=chunk.language,
                        ))
        return result


chunker = CodeChunker(
    chunk_size=settings.chunk_size_tokens,
    overlap=settings.chunk_overlap_tokens,
)