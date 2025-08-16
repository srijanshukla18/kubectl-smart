# Contributing to kubectl-smart

Thanks for your interest in contributing! This project aims to provide a fast, safe, and helpful kubectl plugin for SREs.

## Getting started
- Python 3.11+
- `kubectl` available in PATH
- A Kubernetes cluster (Minikube or KinD)

## Setup
```
./install.sh
```

## Development workflow
- Run tests against Minikube fixtures:
```
./test-setup-minikube.sh
./test.sh
```
- Lint and type-check (suggested): ruff, mypy

## Pull requests
- Keep changes focused and add/adjust tests.
- Ensure `test.sh` passes on a local Minikube.
- Update `README.md`/`examples.md` if user-facing behavior changes.

## Code style
- Prefer clear, explicit names; avoid 1–2 letter vars.
- Handle edge cases first; avoid deep nesting.
- Add short docstrings for non-trivial functions.

## Reporting issues
- Include CLI command, cluster type, and relevant excerpts of output.

Thanks again for helping improve kubectl-smart!

