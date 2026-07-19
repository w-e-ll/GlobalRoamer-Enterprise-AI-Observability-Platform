#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path

from setuptools import find_packages, setup

BASE_DIR = Path(__file__).parent
README_PATH = BASE_DIR / "README.md"


def read_readme() -> str:
    if README_PATH.exists():
        return README_PATH.read_text(encoding="utf-8")
    return ""


setup(
    name="globalroamer-ai-observability",
    version="0.1.0",
    description="AI-assisted telecom roaming diagnostics and operational intelligence platform.",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="Valentin Sheboldaev",
    python_requires=">=3.11",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "python-dotenv>=1.0.1",
        "PyYAML>=6.0.2",
        "openai>=1.35.0",
        "chromadb>=0.5.3",
        "tiktoken>=0.7.0",
        "numpy>=1.26.4",
        "pandas>=2.2.2",
        "pydantic>=2.8.2",
        "tenacity>=8.5.0",
        "python-json-logger>=2.0.7",
        "jinja2>=3.1.4",
        "markdown>=3.6",
        "aiofiles>=24.1.0",
        "orjson>=3.10.6",
    ],
    extras_require={
        "ui": [
            "streamlit>=1.36.0",
            "plotly>=5.22.0",
        ],
        "dev": [
            "pytest>=8.2.2",
            "pytest-mock>=3.14.0",
            "black>=24.4.2",
            "flake8>=7.1.0",
            "isort>=5.13.2",
        ],
        "api": [
            "fastapi>=0.111.0",
            "uvicorn>=0.30.1",
        ],
        "local-ai": [
            "sentence-transformers>=3.0.1",
        ],
    },
    entry_points={
        "console_scripts": [
            "globalroamer-ai-ingest=globalroamer_ai.ingest_main:main",
            "globalroamer-ai-analyze=globalroamer_ai.analyze_main:main",
            "globalroamer-ai-report=globalroamer_ai.report_main:main",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Operating System :: POSIX :: Linux",
        "Operating System :: Microsoft :: Windows",
        "License :: Other/Proprietary License",
        "Intended Audience :: Telecommunications Industry",
        "Topic :: System :: Monitoring",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords=[
        "ai",
        "rag",
        "telecom",
        "roaming",
        "observability",
        "telemetry",
        "vector-search",
        "embeddings",
        "monitoring",
        "root-cause-analysis",
        "operational-intelligence",
        "llm",
        "chromadb",
        "streamlit",
        "backend-engineering",
    ],
    zip_safe=False,
)
