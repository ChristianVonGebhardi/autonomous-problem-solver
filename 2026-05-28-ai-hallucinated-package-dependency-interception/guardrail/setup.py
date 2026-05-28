from setuptools import setup, find_packages

setup(
    name="guardrail-cli",
    version="0.1.0",
    description="AI-Hallucinated Package Dependency Interception",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="GuardRail Contributors",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "httpx>=0.27.0",
        "aiohttp>=3.9.0",
        "anyio>=4.0.0",
        "click>=8.1.7",
        "rich>=13.7.0",
        "aiosqlite>=0.20.0",
        "rapidfuzz>=3.6.0",
        "jellyfish>=1.0.3",
        "tomli>=2.0.1; python_version < '3.11'",
        "jsonschema>=4.21.1",
    ],
    entry_points={
        "console_scripts": [
            "guardrail=cli.main:cli",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Security",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)