"""
Slopsquatting Heuristic Engine.

Detects AI-hallucinated package names using:
1. Edit distance to known-good packages (typosquatting detection)
2. AI-generated naming pattern detection (n-gram scoring, structural patterns)
3. Common confusable prefix/suffix patterns
"""
from __future__ import annotations
import re
import logging
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass

from rapidfuzz import fuzz, process as rfprocess
from rapidfuzz.distance import Levenshtein

from .models import Ecosystem, HeuristicResult

logger = logging.getLogger(__name__)

# ─────────────────────────── Well-known package corpuses ───────────────────────────
# Top PyPI packages (by download count) - used for typosquat detection
TOP_PYPI_PACKAGES: List[str] = [
    "numpy", "pandas", "requests", "scipy", "matplotlib", "pillow", "flask",
    "django", "sqlalchemy", "boto3", "botocore", "urllib3", "certifi",
    "charset-normalizer", "idna", "six", "python-dateutil", "pytz",
    "pyyaml", "packaging", "setuptools", "wheel", "pip", "cryptography",
    "cffi", "pycparser", "attrs", "click", "colorama", "rich",
    "fastapi", "uvicorn", "starlette", "pydantic", "httpx", "aiohttp",
    "pytest", "pytest-cov", "black", "mypy", "pylint", "flake8",
    "isort", "tox", "coverage", "mock", "responses", "hypothesis",
    "tensorflow", "torch", "scikit-learn", "keras", "transformers",
    "openai", "anthropic", "langchain", "llamaindex", "chromadb",
    "redis", "celery", "kombu", "sqlparse", "psycopg2", "pymongo",
    "elasticsearch", "stripe", "twilio", "sendgrid", "aws-cdk-lib",
    "google-cloud-storage", "google-auth", "azure-storage-blob",
    "paramiko", "fabric", "ansible", "docker", "kubernetes",
    "asyncio", "aiofiles", "anyio", "trio", "tornado", "gevent",
    "lxml", "beautifulsoup4", "selenium", "playwright", "scrapy",
    "arrow", "pendulum", "humanize", "babel", "jinja2", "mako",
    "marshmallow", "cerberus", "voluptuous", "jsonschema", "pydantic",
    "alembic", "peewee", "tortoise-orm", "mongoengine", "pymysql",
    "psutil", "py-cpuinfo", "memory-profiler", "line-profiler",
    "loguru", "structlog", "python-json-logger", "sentry-sdk",
    "python-dotenv", "dynaconf", "decouple", "environs",
    "pathlib", "watchdog", "schedule", "apscheduler", "rq", "dramatiq",
    "nmap", "scapy", "pexpect", "pyserial", "pyusb",
    "pygments", "termcolor", "tqdm", "alive-progress",
    "typer", "argparse", "docopt", "plumbum",
    "openpyxl", "xlrd", "xlwt", "csv", "tabulate",
    "pypdf2", "reportlab", "weasyprint", "fpdf",
    "jwt", "pyjwt", "passlib", "bcrypt", "argon2-cffi",
    "itsdangerous", "werkzeug", "wtforms",
    "httplib2", "grpcio", "protobuf", "thrift", "zeromq", "pyzmq",
]

# Top npm packages
TOP_NPM_PACKAGES: List[str] = [
    "react", "react-dom", "vue", "angular", "svelte", "next", "nuxt",
    "express", "fastify", "koa", "hapi", "nestjs",
    "lodash", "underscore", "ramda", "immutable",
    "axios", "node-fetch", "superagent", "got", "ky",
    "moment", "date-fns", "dayjs", "luxon",
    "webpack", "vite", "rollup", "parcel", "esbuild",
    "babel", "@babel/core", "@babel/preset-env", "@babel/preset-react",
    "typescript", "ts-node", "tsx",
    "jest", "mocha", "jasmine", "vitest", "chai", "sinon",
    "eslint", "prettier", "stylelint",
    "tailwindcss", "bootstrap", "material-ui", "@mui/material",
    "redux", "zustand", "mobx", "recoil", "jotai",
    "graphql", "apollo-client", "@apollo/client", "relay",
    "mongoose", "sequelize", "typeorm", "prisma", "drizzle-orm",
    "socket.io", "ws", "socket.io-client",
    "jsonwebtoken", "passport", "bcrypt", "argon2",
    "dotenv", "config", "convict",
    "uuid", "nanoid", "shortid",
    "sharp", "jimp", "canvas",
    "cheerio", "puppeteer", "playwright",
    "stripe", "paypal-rest-sdk",
    "aws-sdk", "@aws-sdk/client-s3", "firebase", "@firebase/app",
    "nodemailer", "sendgrid", "@sendgrid/mail",
    "multer", "busboy", "formidable",
    "compression", "cors", "helmet", "morgan",
    "pm2", "forever", "nodemon",
    "commander", "yargs", "minimist", "meow",
    "chalk", "ora", "inquirer", "prompts",
    "fs-extra", "glob", "chokidar", "rimraf",
    "semver", "npm", "yarn", "pnpm",
    "jest-mock", "@testing-library/react", "enzyme",
    "storybook", "@storybook/react",
    "zod", "yup", "joi", "ajv",
    "i18next", "react-i18next", "vue-i18n",
    "next-auth", "@auth0/nextjs-auth0",
    "framer-motion", "react-spring", "gsap",
    "d3", "chart.js", "recharts", "victory",
    "immer", "produce",
    "rxjs", "rxjs-compat",
    "class-transformer", "class-validator", "reflect-metadata",
]

# Top crates.io packages
TOP_CARGO_PACKAGES: List[str] = [
    "serde", "serde_json", "tokio", "async-std", "rayon",
    "clap", "structopt", "argh", "pico-args",
    "anyhow", "thiserror", "eyre", "color-eyre",
    "tracing", "log", "env_logger", "fern",
    "reqwest", "hyper", "actix-web", "axum", "warp", "rocket",
    "sqlx", "diesel", "sea-orm", "rusqlite",
    "rand", "uuid", "chrono", "time",
    "regex", "lazy_static", "once_cell",
    "itertools", "either", "derivative",
    "bytes", "byteorder", "nom", "pest",
    "crossbeam", "parking_lot", "dashmap",
    "hashbrown", "indexmap", "ahash",
    "num", "num-traits", "num-bigint",
    "image", "rusttype", "ttf-parser",
    "winapi", "nix", "libc",
    "openssl", "rustls", "ring", "sha2", "hmac",
    "base64", "hex", "encoding",
    "tempfile", "dirs", "walkdir",
    "cargo", "semver", "toml", "config",
    "futures", "pin-project", "async-trait",
    "tower", "tower-http", "tonic",
    "prost", "tungstenite", "ws",
    "redis", "mongodb", "elasticsearch",
    "criterion", "proptest", "quickcheck",
    "mockall", "wiremock",
    "clap_derive", "structopt-derive",
]

ECOSYSTEM_PACKAGES: Dict[str, List[str]] = {
    "pypi": TOP_PYPI_PACKAGES,
    "npm": TOP_NPM_PACKAGES,
    "cargo": TOP_CARGO_PACKAGES,
    "go": [],  # Go modules have unique naming, skip corpus-based checks
    "maven": [],
}

# ─────────────────────────── AI naming pattern detection ───────────────────────────

# Patterns commonly seen in AI-hallucinated package names
AI_HALLUCINATION_PATTERNS = [
    # Overly descriptive compound names that feel "AI-generated"
    (r"^[a-z]+-[a-z]+-[a-z]+-[a-z]+-[a-z]+$", 0.4, "overly-hyphenated-name"),
    # "python-" prefix on existing package names
    (r"^python-[a-z]{3,}$", 0.2, "python-prefix-pattern"),
    # Nonsense combinations like "numpy-utils-helper"
    (r"^(numpy|pandas|torch|tensorflow|scipy)[-_](utils?|helpers?|tools?|ext|extra|plus)$", 0.5, "known-package-suffix"),
    # Version numbers in package names (unusual)
    (r"[0-9]+\.[0-9]+", 0.3, "version-in-name"),
    # Underscore-separated names that closely resemble hyphenated popular packages
    (r"^[a-z]+_[a-z]+_[a-z]+_[a-z]+$", 0.3, "excessive-underscores"),
    # "ai-" or "ml-" prefixes on utility names
    (r"^(ai|ml|llm|gpt|nlp)[-_][a-z]+$", 0.25, "ai-prefix-pattern"),
    # Names ending in common AI-suggested suffixes
    (r"[-_](wrapper|toolkit|suite|bundle|framework|sdk|api|lib|core|base)$", 0.15, "generic-ai-suffix"),
    # Names that look like they describe functionality too literally
    (r"^[a-z]+-to-[a-z]+$", 0.2, "literal-converter-pattern"),
    # Camel case in package names (unusual for most ecosystems)
    (r"[a-z][A-Z][a-z]", 0.3, "camelcase-in-package-name"),
    # Names with common brand+utils pattern
    (r"^(aws|gcp|azure|google|microsoft|amazon)[-_](utils?|helpers?|common|tools?)$", 0.35, "cloud-utils-pattern"),
]

# Suspicious length ranges
MIN_SUSPICIOUS_LENGTH = 2
MAX_SUSPICIOUS_LENGTH = 60
VERY_SHORT_NAME_THRESHOLD = 3
VERY_LONG_NAME_THRESHOLD = 40


class HeuristicEngine:
    """
    Computes heuristic risk scores for package names.
    
    Combines:
    - Edit distance to known-good corpus
    - AI naming pattern detection  
    - Structural analysis
    """

    def __init__(self, ecosystem: Optional[str] = None):
        self.ecosystem = ecosystem

    def _get_corpus(self, ecosystem: str) -> List[str]:
        return ECOSYSTEM_PACKAGES.get(ecosystem.lower(), [])

    def _compute_edit_distance_score(
        self, package_name: str, corpus: List[str]
    ) -> Tuple[float, List[str], Optional[int]]:
        """
        Check if package_name is suspiciously close to known packages.
        Returns (score, similar_packages, min_edit_distance).
        """
        if not corpus:
            return 0.0, [], None

        name_lower = package_name.lower()

        # Skip exact matches (they're fine)
        if name_lower in {p.lower() for p in corpus}:
            return 0.0, [], 0

        # Find closest matches using rapidfuzz
        # Use token_set_ratio for multi-word package names
        matches = rfprocess.extract(
            name_lower,
            [p.lower() for p in corpus],
            scorer=fuzz.ratio,
            limit=5,
            score_cutoff=60,
        )

        if not matches:
            return 0.0, [], None

        # Also compute raw Levenshtein distances for the closest matches
        similar = []
        min_dist = None
        for match_name, score, _ in matches:
            dist = Levenshtein.distance(name_lower, match_name)
            if min_dist is None or dist < min_dist:
                min_dist = dist
            # If edit distance is 1 or 2, this is highly suspicious
            if dist <= 2:
                similar.append(match_name)

        if not similar and matches:
            # Include best match even if not within edit distance 2
            similar = [matches[0][0]]

        # Score: edit distance 1 → very suspicious, 2 → suspicious, 3+ → less so
        if min_dist is not None:
            if min_dist == 1:
                score = 0.85
            elif min_dist == 2:
                score = 0.65
            elif min_dist == 3:
                score = 0.35
            elif min_dist <= 5:
                score = 0.15
            else:
                score = 0.0
        else:
            score = 0.0

        return score, similar, min_dist

    def _compute_ai_pattern_score(self, package_name: str) -> Tuple[float, List[str]]:
        """
        Check for AI hallucination naming patterns.
        Returns (score, matched_flags).
        """
        total_score = 0.0
        flags = []

        for pattern, weight, flag_name in AI_HALLUCINATION_PATTERNS:
            if re.search(pattern, package_name, re.IGNORECASE):
                total_score += weight
                flags.append(flag_name)

        # Length-based heuristics
        name_len = len(package_name)
        if name_len < VERY_SHORT_NAME_THRESHOLD:
            total_score += 0.1
            flags.append("very-short-name")
        elif name_len > VERY_LONG_NAME_THRESHOLD:
            total_score += 0.2
            flags.append("very-long-name")

        # Check for random-looking character sequences
        if re.search(r"[a-z]{8,}", package_name.replace("-", "").replace("_", "")):
            consonant_ratio = len(re.findall(r"[bcdfghjklmnpqrstvwxyz]", package_name.lower())) / max(len(package_name), 1)
            if consonant_ratio > 0.8:
                total_score += 0.3
                flags.append("high-consonant-ratio")

        # Check for mixed separators (both - and _)
        if "-" in package_name and "_" in package_name:
            total_score += 0.15
            flags.append("mixed-separators")

        # Normalize to 0-1
        normalized = min(total_score, 1.0)
        return normalized, flags

    def _compute_structural_score(self, package_name: str, ecosystem: str) -> Tuple[float, List[str]]:
        """
        Check structural validity per ecosystem conventions.
        """
        flags = []
        score = 0.0

        # PyPI: should match [a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?
        if ecosystem == "pypi":
            if not re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9._\-]*[a-zA-Z0-9])?$", package_name):
                score += 0.4
                flags.append("invalid-pypi-name-format")

        # npm: should be lowercase, no spaces
        elif ecosystem == "npm":
            if not re.match(r"^(@[a-z0-9-]+\/)?[a-z0-9][a-z0-9._\-]*$", package_name):
                score += 0.35
                flags.append("invalid-npm-name-format")

        # Cargo: should be [A-Za-z][A-Za-z0-9_-]*
        elif ecosystem == "cargo":
            if not re.match(r"^[A-Za-z][A-Za-z0-9_\-]*$", package_name):
                score += 0.35
                flags.append("invalid-cargo-name-format")

        return score, flags

    def analyze(self, package_name: str, ecosystem: str) -> HeuristicResult:
        """Full heuristic analysis for a package name."""
        corpus = self._get_corpus(ecosystem)

        # Edit distance check
        ed_score, similar_pkgs, min_dist = self._compute_edit_distance_score(
            package_name, corpus
        )

        # AI pattern check
        ai_score, ai_flags = self._compute_ai_pattern_score(package_name)

        # Structural check
        struct_score, struct_flags = self._compute_structural_score(package_name, ecosystem)

        # Combine scores (weighted)
        # Edit distance is most important signal
        combined_score = (
            ed_score * 0.5 +
            ai_score * 0.35 +
            struct_score * 0.15
        )

        all_flags = []
        if ed_score > 0.3:
            all_flags.append(f"similar-to-known-package:{','.join(similar_pkgs[:2])}")
        all_flags.extend(ai_flags)
        all_flags.extend(struct_flags)

        return HeuristicResult(
            score=min(combined_score, 1.0),
            flags=all_flags,
            similar_packages=similar_pkgs,
            edit_distance=min_dist,
            ai_pattern_score=ai_score,
        )