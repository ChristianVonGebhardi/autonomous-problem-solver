"""Tests for manifest file parsers."""
import os
import json
import tempfile
import pytest
from pathlib import Path
from core.parsers import parse_manifest, _parse_requirements_txt, _parse_npm, _parse_cargo
from core.models import Ecosystem


class TestRequirementsTxt:
    def test_simple_requirements(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("requests==2.31.0\nnumpy>=1.24.0\npandas\n")
        packages = parse_manifest(str(req), Ecosystem.PYPI)
        assert "requests" in packages
        assert "numpy" in packages
        assert "pandas" in packages

    def test_comments_ignored(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("# This is a comment\nrequests==2.31.0\n# Another comment\n")
        packages = parse_manifest(str(req), Ecosystem.PYPI)
        assert packages == ["requests"]

    def test_empty_lines_ignored(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("\nrequests\n\nnumpy\n\n")
        packages = parse_manifest(str(req), Ecosystem.PYPI)
        assert "requests" in packages
        assert "numpy" in packages

    def test_flags_ignored(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("-r other.txt\n--index-url https://...\nrequests\n")
        packages = parse_manifest(str(req), Ecosystem.PYPI)
        assert packages == ["requests"]

    def test_version_specifiers_stripped(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text(
            "requests~=2.31.0\nnumpy!=1.0\npandas>=1.0,<=2.0\ncryptography[ssh]>=40\n"
        )
        packages = parse_manifest(str(req), Ecosystem.PYPI)
        assert "requests" in packages
        assert "numpy" in packages
        assert "pandas" in packages
        assert "cryptography" in packages

    def test_inline_comments_stripped(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("requests==2.31.0  # HTTP library\nnumpy  # arrays\n")
        packages = parse_manifest(str(req), Ecosystem.PYPI)
        assert "requests" in packages
        assert "numpy" in packages

    def test_empty_file(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("")
        packages = parse_manifest(str(req), Ecosystem.PYPI)
        assert packages == []


class TestPackageJson:
    def test_dependencies_parsed(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({
            "name": "my-app",
            "dependencies": {
                "express": "^4.18.0",
                "lodash": "^4.17.21"
            },
            "devDependencies": {
                "jest": "^29.0.0",
                "typescript": "^5.0.0"
            }
        }))
        packages = parse_manifest(str(pkg), Ecosystem.NPM)
        assert "express" in packages
        assert "lodash" in packages
        assert "jest" in packages
        assert "typescript" in packages

    def test_empty_package_json(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text('{"name": "test"}')
        packages = parse_manifest(str(pkg), Ecosystem.NPM)
        assert packages == []

    def test_scoped_packages(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({
            "dependencies": {
                "@babel/core": "^7.0.0",
                "@types/node": "^20.0.0"
            }
        }))
        packages = parse_manifest(str(pkg), Ecosystem.NPM)
        assert "@babel/core" in packages
        assert "@types/node" in packages

    def test_deduplication(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({
            "dependencies": {"express": "^4.0.0"},
            "devDependencies": {"express": "^4.0.0"}  # duplicate
        }))
        packages = parse_manifest(str(pkg), Ecosystem.NPM)
        assert packages.count("express") == 1


class TestCargoToml:
    def test_basic_cargo(self, tmp_path):
        cargo = tmp_path / "Cargo.toml"
        cargo.write_text("""
[package]
name = "my-crate"
version = "0.1.0"

[dependencies]
serde = { version = "1.0", features = ["derive"] }
tokio = "1.0"

[dev-dependencies]
mockall = "0.11"
""")
        packages = parse_manifest(str(cargo), Ecosystem.CARGO)
        assert "serde" in packages
        assert "tokio" in packages
        assert "mockall" in packages

    def test_empty_cargo(self, tmp_path):
        cargo = tmp_path / "Cargo.toml"
        cargo.write_text('[package]\nname = "test"\nversion = "0.1.0"\n')
        packages = parse_manifest(str(cargo), Ecosystem.CARGO)
        assert packages == []


class TestGoMod:
    def test_go_mod_parsing(self, tmp_path):
        gomod = tmp_path / "go.mod"
        gomod.write_text("""module example.com/myapp

go 1.21

require (
    github.com/gin-gonic/gin v1.9.1
    github.com/stretchr/testify v1.8.4
)

require github.com/google/uuid v1.3.0
""")
        packages = parse_manifest(str(gomod), Ecosystem.GO)
        assert "github.com/gin-gonic/gin" in packages
        assert "github.com/stretchr/testify" in packages
        assert "github.com/google/uuid" in packages

    def test_empty_go_mod(self, tmp_path):
        gomod = tmp_path / "go.mod"
        gomod.write_text("module example.com/test\n\ngo 1.21\n")
        packages = parse_manifest(str(gomod), Ecosystem.GO)
        assert packages == []


class TestEcosystemDetection:
    def test_requirements_txt_detected(self):
        eco = Ecosystem.from_manifest("requirements.txt")
        assert eco == Ecosystem.PYPI

    def test_package_json_detected(self):
        eco = Ecosystem.from_manifest("package.json")
        assert eco == Ecosystem.NPM

    def test_cargo_toml_detected(self):
        eco = Ecosystem.from_manifest("Cargo.toml")
        assert eco == Ecosystem.CARGO

    def test_go_mod_detected(self):
        eco = Ecosystem.from_manifest("go.mod")
        assert eco == Ecosystem.GO

    def test_pyproject_toml_detected(self):
        eco = Ecosystem.from_manifest("pyproject.toml")
        assert eco == Ecosystem.PYPI

    def test_unknown_returns_none(self):
        eco = Ecosystem.from_manifest("unknown.xyz")
        assert eco is None