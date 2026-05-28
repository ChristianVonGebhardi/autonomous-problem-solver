"""
Manifest file parsers.

Supports: requirements.txt, package.json, Cargo.toml, go.mod, pyproject.toml
"""
from __future__ import annotations
import json
import re
import os
import sys
import logging
from typing import List, Optional
from pathlib import Path

from .models import Ecosystem

logger = logging.getLogger(__name__)

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            tomllib = None


def parse_manifest(path: str, ecosystem: Ecosystem) -> List[str]:
    """Parse a manifest file and return list of package names."""
    parsers = {
        Ecosystem.PYPI: _parse_pypi,
        Ecosystem.NPM: _parse_npm,
        Ecosystem.CARGO: _parse_cargo,
        Ecosystem.GO: _parse_go,
        Ecosystem.MAVEN: _parse_maven,
    }
    parser = parsers.get(ecosystem)
    if not parser:
        raise ValueError(f"No parser for ecosystem: {ecosystem.value}")
    return parser(path)


def _parse_pypi(path: str) -> List[str]:
    """Parse various Python manifest formats."""
    basename = os.path.basename(path)
    
    if basename == "requirements.txt" or basename.startswith("requirements"):
        return _parse_requirements_txt(path)
    elif basename == "pyproject.toml":
        return _parse_pyproject_toml(path)
    elif basename == "setup.cfg":
        return _parse_setup_cfg(path)
    elif basename == "Pipfile":
        return _parse_pipfile(path)
    else:
        # Try requirements.txt format as fallback
        return _parse_requirements_txt(path)


def _parse_requirements_txt(path: str) -> List[str]:
    """Parse requirements.txt format."""
    packages = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                # Handle inline comments
                line = line.split("#")[0].strip()
                if not line:
                    continue
                # Extract package name (before version specifiers)
                # Handle: pkg==1.0, pkg>=1.0, pkg~=1.0, pkg[extra], pkg @ url
                match = re.match(
                    r"^([A-Za-z0-9]([A-Za-z0-9._\-]*[A-Za-z0-9])?)",
                    line
                )
                if match:
                    pkg_name = match.group(1).strip()
                    if pkg_name:
                        packages.append(pkg_name)
    except FileNotFoundError:
        logger.error("File not found: %s", path)
    except Exception as e:
        logger.error("Error parsing %s: %s", path, e)
    return packages


def _parse_pyproject_toml(path: str) -> List[str]:
    """Parse pyproject.toml dependencies."""
    if tomllib is None:
        logger.warning("tomllib not available, cannot parse pyproject.toml")
        return []
    
    packages = []
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        
        # PEP 621 style
        project = data.get("project", {})
        deps = project.get("dependencies", [])
        for dep in deps:
            match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._\-]*)", dep)
            if match:
                packages.append(match.group(1))
        
        # Poetry style
        poetry = data.get("tool", {}).get("poetry", {})
        for dep_section in ["dependencies", "dev-dependencies"]:
            for pkg_name in poetry.get(dep_section, {}):
                if pkg_name.lower() not in ("python",):
                    packages.append(pkg_name)
        
        # PDM / Flit style
        optional_deps = project.get("optional-dependencies", {})
        for group_deps in optional_deps.values():
            for dep in group_deps:
                match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._\-]*)", dep)
                if match:
                    packages.append(match.group(1))
                    
    except Exception as e:
        logger.error("Error parsing %s: %s", path, e)
    
    return list(dict.fromkeys(packages))  # deduplicate preserving order


def _parse_setup_cfg(path: str) -> List[str]:
    """Parse setup.cfg install_requires."""
    import configparser
    packages = []
    try:
        config = configparser.ConfigParser()
        config.read(path)
        if config.has_option("options", "install_requires"):
            deps = config.get("options", "install_requires").strip().split("\n")
            for dep in deps:
                dep = dep.strip()
                if dep and not dep.startswith("#"):
                    match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._\-]*)", dep)
                    if match:
                        packages.append(match.group(1))
    except Exception as e:
        logger.error("Error parsing %s: %s", path, e)
    return packages


def _parse_pipfile(path: str) -> List[str]:
    """Parse Pipfile [packages] and [dev-packages]."""
    if tomllib is None:
        logger.warning("tomllib not available, cannot parse Pipfile")
        return []
    packages = []
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        for section in ("packages", "dev-packages"):
            for pkg in data.get(section, {}):
                if pkg.lower() not in ("python_requires",):
                    packages.append(pkg)
    except Exception as e:
        logger.error("Error parsing %s: %s", path, e)
    return packages


def _parse_npm(path: str) -> List[str]:
    """Parse package.json dependencies."""
    packages = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            for pkg_name in data.get(section, {}):
                packages.append(pkg_name)
    except FileNotFoundError:
        logger.error("File not found: %s", path)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error in %s: %s", path, e)
    except Exception as e:
        logger.error("Error parsing %s: %s", path, e)
    
    return list(dict.fromkeys(packages))


def _parse_cargo(path: str) -> List[str]:
    """Parse Cargo.toml dependencies."""
    if tomllib is None:
        logger.warning("tomllib not available, cannot parse Cargo.toml")
        return []
    
    packages = []
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        
        for section in ("dependencies", "dev-dependencies", "build-dependencies"):
            for pkg_name in data.get(section, {}):
                packages.append(pkg_name)
        
        # Workspace dependencies
        workspace = data.get("workspace", {})
        for pkg_name in workspace.get("dependencies", {}):
            packages.append(pkg_name)
            
    except Exception as e:
        logger.error("Error parsing %s: %s", path, e)
    
    return list(dict.fromkeys(packages))


def _parse_go(path: str) -> List[str]:
    """Parse go.mod require directives."""
    packages = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Match: require github.com/user/repo v1.0.0
        single_require = re.findall(
            r"^require\s+(\S+)\s+\S+",
            content,
            re.MULTILINE,
        )
        packages.extend(single_require)
        
        # Match require ( ... ) blocks
        blocks = re.findall(
            r"require\s*\((.*?)\)",
            content,
            re.DOTALL,
        )
        for block in blocks:
            for line in block.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("//"):
                    match = re.match(r"^(\S+)\s+", line)
                    if match:
                        packages.append(match.group(1))
    except Exception as e:
        logger.error("Error parsing %s: %s", path, e)
    
    return list(dict.fromkeys(packages))


def _parse_maven(path: str) -> List[str]:
    """Parse pom.xml dependencies."""
    import xml.etree.ElementTree as ET
    packages = []
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        
        # Handle namespace
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"
        
        for dep in root.findall(f".//{ns}dependency"):
            group_id = dep.find(f"{ns}groupId")
            artifact_id = dep.find(f"{ns}artifactId")
            if group_id is not None and artifact_id is not None:
                packages.append(f"{group_id.text}:{artifact_id.text}")
    except Exception as e:
        logger.error("Error parsing %s: %s", path, e)
    
    return list(dict.fromkeys(packages))