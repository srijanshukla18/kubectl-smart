# Contributing to kubectl-smart

Thanks for your interest in contributing! This project is in **early beta** and aims to provide a helpful kubectl plugin for Kubernetes debugging.

## Project Status
- 🔬 **Beta/v0.x** - Core functionality works, but expect changes
- 📈 **Actively seeking feedback** - Real-world usage reports especially valuable
- 🐛 **Bug reports welcome** - Help us identify edge cases and issues

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

## Beta Expectations
- APIs and CLI interfaces may change between versions
- Some features are still evolving based on user feedback
- Documentation may lag behind latest changes
- Performance characteristics may vary across different cluster sizes

Thanks for helping shape kubectl-smart's development!

