# Google-Style Python Docstrings Reference

## Purpose
Provide a concise, repository-local guide for writing high-quality Google-style
Python docstrings in `docctl`.

## Primary Source
- Google Python Style Guide (Docstrings):
  <https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings>

## What Good Google-Style Docstrings Do
1. Start with a one-line summary sentence in imperative mood.
2. Explain behavior and intent, not implementation trivia.
3. Describe arguments and return values with clear semantic meaning.
4. Call out raised exceptions and any non-obvious side effects.
5. Stay consistent with function signatures and actual runtime behavior.

## Standard Section Pattern
Use only the sections that apply:
- `Args:`
- `Returns:`
- `Raises:`
- `Yields:`

Example skeleton:

```python
def load_index(path: str, strict: bool = True) -> Index:
    """Load a persisted index from disk.

    Args:
        path: Filesystem location of the persisted index.
        strict: Whether to fail when metadata validation errors are found.

    Returns:
        A fully initialized `Index` instance.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If index metadata is invalid and `strict` is True.
    """
```

## Repository-Specific Guidance
- Apply docstrings to public APIs first (`src/docctl/*.py`).
- Keep docstrings short, specific, and operationally useful for agent workflows.
- Update docstrings in the same change set when behavior changes.
