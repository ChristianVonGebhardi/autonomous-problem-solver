import pytest
from app.services.chunker import CodeChunker, CodeChunk


@pytest.fixture
def chunker():
    return CodeChunker(chunk_size=50, overlap=10)


def test_chunk_python_file(chunker):
    code = '''
def hello_world():
    """Say hello."""
    print("Hello, World!")


class MyClass:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"Hello, {self.name}"


def another_function():
    return 42
'''
    chunks = chunker.chunk_file("test.py", code, "test_repo")
    assert len(chunks) > 0
    # Should detect functions and classes
    chunk_types = {c.chunk_type for c in chunks}
    assert "function" in chunk_types or "class" in chunk_types


def test_chunk_javascript_file(chunker):
    code = '''
export function processData(data) {
    return data.map(item => item.value);
}

class DataProcessor {
    constructor(config) {
        this.config = config;
    }

    process(items) {
        return items.filter(Boolean);
    }
}

const helper = async (url) => {
    const resp = await fetch(url);
    return resp.json();
};
'''
    chunks = chunker.chunk_file("utils.js", code, "test_repo")
    assert len(chunks) > 0


def test_chunk_markdown_file(chunker):
    content = '''# Project Overview

This is the main documentation.

## Architecture

We use microservices with the following components.

### Services

List of services here.

## Getting Started

Installation instructions.
'''
    chunks = chunker.chunk_file("README.md", content, "test_repo")
    assert len(chunks) > 0
    types = {c.chunk_type for c in chunks}
    assert "documentation" in types


def test_chunk_id_stable(chunker):
    code = "def foo(): pass"
    chunks1 = chunker.chunk_file("test.py", code, "repo1")
    chunks2 = chunker.chunk_file("test.py", code, "repo1")
    if chunks1 and chunks2:
        assert chunks1[0].chunk_id == chunks2[0].chunk_id


def test_skip_large_content(chunker):
    chunker.chunk_size = 10
    large_content = "\n".join([f"line {i}: " + "x" * 50 for i in range(1000)])
    chunks = chunker.chunk_file("large.py", large_content, "repo")
    # Should produce multiple chunks
    assert len(chunks) > 1


def test_to_dict(chunker):
    code = "def test(): return True"
    chunks = chunker.chunk_file("test.py", code, "myrepo")
    if chunks:
        d = chunks[0].to_dict()
        assert "chunk_id" in d
        assert "content" in d
        assert "file_path" in d
        assert "repo_name" in d
        assert d["repo_name"] == "myrepo"


def test_should_skip():
    chunker = CodeChunker()
    assert chunker.should_skip("image.png") is True
    assert chunker.should_skip("node_modules/lib/index.js") is True
    assert chunker.should_skip("src/main.py") is False