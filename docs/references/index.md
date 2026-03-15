# References Index

Curated authoritative sources used for implementation and operations decisions.

| id | source | authority_type | status | notes |
|---|---|---|---|---|
| REF-0001 | Chroma Documentation | official vendor documentation | active | local persistence and query behavior |
| REF-0002 | LlamaIndex Documentation | primary project documentation | active | sentence-aware chunking behavior |
| REF-0003 | OpenAI Codex Security Docs | official vendor documentation | active | shell approvals and sandbox model |
| REF-0004 | Ruff Documentation | primary project documentation | active | lint and formatter baseline policy |
| REF-0005 | mypy Documentation | primary project documentation | active | proposed static typing checks |
| REF-0006 | Bandit Documentation | primary project documentation | active | proposed security linting checks |
| REF-0007 | import-linter Documentation | primary project documentation | active | proposed architecture boundary checks |
| REF-0008 | Google Python Style Guide (Docstrings) | primary project documentation | active | Google-style docstring structure and quality guidance |
| REF-0009 | PyPA Packaging Guide: Publishing package distribution releases using GitHub Actions CI/CD workflows | primary project documentation | active | trusted publishing workflow split and environment guidance |
| REF-0010 | PyPI Trusted Publishers: Creating a project through OIDC | official vendor documentation | active | pending publisher registration and first-publish behavior |
| REF-0011 | uv Documentation: Projects and build configuration | primary project documentation | active | explicit build-system behavior and uv package builds |
| REF-0012 | python-semantic-release Documentation | primary project documentation | active | conventional commit parsing and GitHub release automation |
| REF-0013 | Conventional Commits 1.0.0 | standards body / specification | active | commit message contract for semantic version derivation |
| REF-0014 | Hugging Face Model Card: jinaai/jina-embeddings-v5-text-small-retrieval | primary project documentation | active | default embedding model license caveat |
| REF-0015 | Sentence Transformers Documentation | primary project documentation | active | retrieve-rerank pattern and CrossEncoder usage |
| REF-0016 | Hugging Face Model Card: BAAI/bge-reranker-v2-m3 | primary project documentation | active | reranker model behavior and license |
| REF-0017 | Chroma Query & Get Documentation | official vendor documentation | active | local collection query semantics |
| REF-0018 | ChromaDB Go Client Rerankers | primary project documentation | active | confirms client-side rerank pattern, not python runtime contract |
| REF-0019 | Dependabot Options Reference | official vendor documentation | active | schedule, groups, commit-message, and update volume controls |
| REF-0020 | Automating Dependabot with GitHub Actions | official vendor documentation | active | metadata-driven conditional auto-merge automation |
| REF-0021 | Dependency Review Action | official vendor documentation | active | pull request dependency risk gate for supply chain security |
| REF-0022 | Supported Ecosystems for Dependabot and Dependency Graph | official vendor documentation | active | confirms `uv` and `github-actions` ecosystem support context |

## Source Quality Rule
Use authoritative, professional sources (official vendor documentation,
standards bodies, primary project documentation, and reputable security or
operations references), and avoid relying on informal or unverified sources.
