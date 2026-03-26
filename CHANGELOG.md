# CHANGELOG


## v0.3.0 (2026-03-26)

### Bug Fixes

- **ci**: Use available setup-trivy v0.2.6 tag
  ([#30](https://github.com/GeorgesAlkhouri/docctl/pull/30),
  [`5a5dd26`](https://github.com/GeorgesAlkhouri/docctl/commit/5a5dd26059bab395375dd40066b565db6e96b4df))

- **lint**: Satisfy ruff import and B009 rules
  ([#32](https://github.com/GeorgesAlkhouri/docctl/pull/32),
  [`ccf0346`](https://github.com/GeorgesAlkhouri/docctl/commit/ccf034683c6c11fbf86400cc424cefdeaf38df07))

### Chores

- **deps)(deps**: Bump actions/download-artifact from 4 to 8
  ([#20](https://github.com/GeorgesAlkhouri/docctl/pull/20),
  [`a341c47`](https://github.com/GeorgesAlkhouri/docctl/commit/a341c4725a535ebfed799a3621186cd9557ed6f4))

- **deps)(deps**: Bump actions/upload-artifact from 4 to 7
  ([#19](https://github.com/GeorgesAlkhouri/docctl/pull/19),
  [`1230235`](https://github.com/GeorgesAlkhouri/docctl/commit/12302351d5b8eb69fc02d636e94416f9159c1436))

- **deps)(deps**: Bump aquasecurity/setup-trivy
  ([#31](https://github.com/GeorgesAlkhouri/docctl/pull/31),
  [`c38a059`](https://github.com/GeorgesAlkhouri/docctl/commit/c38a0591ffa200b562bb2e40e3a00a3623250c57))

- **deps)(deps**: Bump aquasecurity/setup-trivy from 0.2.5 to 0.2.6 in the actions-patch-minor group
  ([#31](https://github.com/GeorgesAlkhouri/docctl/pull/31),
  [`c38a059`](https://github.com/GeorgesAlkhouri/docctl/commit/c38a0591ffa200b562bb2e40e3a00a3623250c57))

- **deps)(deps**: Bump aquasecurity/trivy-action
  ([#18](https://github.com/GeorgesAlkhouri/docctl/pull/18),
  [`de64c23`](https://github.com/GeorgesAlkhouri/docctl/commit/de64c23468ab0c0231cadcabb457154246869834))

- **deps)(deps**: Bump aquasecurity/trivy-action from 0.34.2 to 0.35.0 in the actions-patch-minor
  group ([#18](https://github.com/GeorgesAlkhouri/docctl/pull/18),
  [`de64c23`](https://github.com/GeorgesAlkhouri/docctl/commit/de64c23468ab0c0231cadcabb457154246869834))

- **deps)(deps**: Bump chromadb from 1.5.2 to 1.5.5
  ([#25](https://github.com/GeorgesAlkhouri/docctl/pull/25),
  [`3240615`](https://github.com/GeorgesAlkhouri/docctl/commit/32406150fa166b3daebc47dc02d01b309631c852))

- **deps)(deps**: Bump llama-index-core from 0.14.15 to 0.14.17
  ([#22](https://github.com/GeorgesAlkhouri/docctl/pull/22),
  [`254e687`](https://github.com/GeorgesAlkhouri/docctl/commit/254e6875fd075f6b85ba8f4c676e2b2c22a2d72b))

- **deps)(deps**: Bump pypdf from 6.7.5 to 6.9.0
  ([#27](https://github.com/GeorgesAlkhouri/docctl/pull/27),
  [`dd1d5f9`](https://github.com/GeorgesAlkhouri/docctl/commit/dd1d5f9ff4b57ab919cdf0f2e56f2056b1c91849))

- **deps)(deps**: Bump sentence-transformers from 5.2.3 to 5.3.0
  ([#24](https://github.com/GeorgesAlkhouri/docctl/pull/24),
  [`ab81a96`](https://github.com/GeorgesAlkhouri/docctl/commit/ab81a96e0ab28b1f5144ceed5271792a1b68fb59))

- **deps-dev)(deps-dev**: Bump ruff from 0.15.5 to 0.15.6 in the uv-dev-patch-minor group
  ([#21](https://github.com/GeorgesAlkhouri/docctl/pull/21),
  [`8949522`](https://github.com/GeorgesAlkhouri/docctl/commit/8949522928be2006bdb0167c1cb575710b0d6807))

- **deps-dev)(deps-dev**: Bump ruff in the uv-dev-patch-minor group
  ([#21](https://github.com/GeorgesAlkhouri/docctl/pull/21),
  [`8949522`](https://github.com/GeorgesAlkhouri/docctl/commit/8949522928be2006bdb0167c1cb575710b0d6807))

- **deps-dev)(deps-dev**: Bump the uv-dev-patch-minor group with 2 updates
  ([#30](https://github.com/GeorgesAlkhouri/docctl/pull/30),
  [`5a5dd26`](https://github.com/GeorgesAlkhouri/docctl/commit/5a5dd26059bab395375dd40066b565db6e96b4df))

### Code Style

- Apply ruff format ([#32](https://github.com/GeorgesAlkhouri/docctl/pull/32),
  [`ccf0346`](https://github.com/GeorgesAlkhouri/docctl/commit/ccf034683c6c11fbf86400cc424cefdeaf38df07))

### Features

- **snapshot**: Add zip import and export workflows
  ([#32](https://github.com/GeorgesAlkhouri/docctl/pull/32),
  [`ccf0346`](https://github.com/GeorgesAlkhouri/docctl/commit/ccf034683c6c11fbf86400cc424cefdeaf38df07))

- **snapshot**: Add zip import/export workflows for index snapshots
  ([#32](https://github.com/GeorgesAlkhouri/docctl/pull/32),
  [`ccf0346`](https://github.com/GeorgesAlkhouri/docctl/commit/ccf034683c6c11fbf86400cc424cefdeaf38df07))

### Refactoring

- Replace copy comprehension with list constructor
  ([#32](https://github.com/GeorgesAlkhouri/docctl/pull/32),
  [`ccf0346`](https://github.com/GeorgesAlkhouri/docctl/commit/ccf034683c6c11fbf86400cc424cefdeaf38df07))

### Testing

- **snapshot**: Cover import/export edge branches
  ([#32](https://github.com/GeorgesAlkhouri/docctl/pull/32),
  [`ccf0346`](https://github.com/GeorgesAlkhouri/docctl/commit/ccf034683c6c11fbf86400cc424cefdeaf38df07))


## v0.2.2 (2026-03-17)

### Bug Fixes

- **packaging**: Remove gpu extra and cpu torch index wiring
  ([#29](https://github.com/GeorgesAlkhouri/docctl/pull/29),
  [`c10c488`](https://github.com/GeorgesAlkhouri/docctl/commit/c10c48893980c8d8ecf52f96f697a3df4540664f))


## v0.2.1 (2026-03-16)

### Bug Fixes

- **ci**: Harden manual release workflow inputs
  ([#28](https://github.com/GeorgesAlkhouri/docctl/pull/28),
  [`40bcc77`](https://github.com/GeorgesAlkhouri/docctl/commit/40bcc775fafff0e518b115e4cb1e547281f96a46))

### Chores

- **release**: Use init mode for changelog generation
  ([#15](https://github.com/GeorgesAlkhouri/docctl/pull/15),
  [`9fdf7e0`](https://github.com/GeorgesAlkhouri/docctl/commit/9fdf7e0fe75b2f8d1d7ffa2ed587c9a178982fc7))

### Continuous Integration

- **deps**: Add Dependabot automation aligned with manual releases
  ([#17](https://github.com/GeorgesAlkhouri/docctl/pull/17),
  [`62fdd91`](https://github.com/GeorgesAlkhouri/docctl/commit/62fdd913389fb5e82a0880845d3ffb76d62843f6))

- **deps**: Add dependabot automation and dependency review gate
  ([#17](https://github.com/GeorgesAlkhouri/docctl/pull/17),
  [`62fdd91`](https://github.com/GeorgesAlkhouri/docctl/commit/62fdd913389fb5e82a0880845d3ffb76d62843f6))

### Documentation

- **skill**: Rename skill to docctl and document rerank controls
  ([#16](https://github.com/GeorgesAlkhouri/docctl/pull/16),
  [`4af9032`](https://github.com/GeorgesAlkhouri/docctl/commit/4af90325b5240bb7ff33891211b99ce56b3399f5))


## v0.2.0 (2026-03-14)

### Features

- **rerank**: Add two-stage retrieval reranking and reproducible benchmark updates
  ([`688c850`](https://github.com/GeorgesAlkhouri/docctl/commit/688c850f73784eb01b7ae9c9d8f11f384c60c77a))


## v0.1.0 (2026-03-12)

- Initial Release
