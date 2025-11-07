# Testing Status & Roadmap

## Current State: Honest Assessment

### Test Coverage: **~15%** (Integration tests only)

**What we have:**
- ✅ Integration test suite (`test.sh`) - 500+ lines of bash tests
- ✅ Tests against live minikube clusters
- ✅ Real kubectl command execution
- ✅ End-to-end workflow validation

**What we DON'T have:**
- ❌ **No unit tests** for individual components
- ❌ **No pytest test suite** (despite configuration in pyproject.toml)
- ❌ **No mocking** of kubectl calls for fast tests
- ❌ **No CI/CD** automated test runs
- ❌ **No code coverage measurement**

### Why the honesty?

We believe in **transparency over marketing**. The previous configuration claimed 90% coverage requirements, but this was aspirational, not reality. This document sets honest expectations and shows our path forward.

---

## What IS Tested (Integration Tests)

Our bash integration test suite (`test.sh`) validates:

1. **Command execution**: All three commands (diag, graph, top) run without crashes
2. **Help text**: All --help flags work correctly
3. **Version checking**: --version returns correct version
4. **Resource types**: All supported resource types (pod, deploy, sts, job, svc, rs, ds)
5. **Exit codes**: Proper exit codes for success/failure scenarios
6. **Namespace handling**: -n flag works correctly
7. **Context switching**: --context flag respected
8. **Error handling**: Graceful failures on missing resources
9. **Real cluster compatibility**: Works against actual minikube/k8s

**Coverage estimate**: ~15% of code paths

---

## What is NOT Tested (Critical Gaps)

### 1. Scoring Engine (`scoring/engine.py`)
- No unit tests for score calculation
- No validation of severity thresholds
- No tests for edge cases (negative scores, overflow, etc.)
- No tests for different weight configurations

### 2. Graph Builder (`graph/builder.py`)
- No tests for cycle detection
- No tests for shortest path algorithms
- No tests for different graph topologies
- No tests for ASCII rendering edge cases

### 3. Parsers (`parsers/`)
- No tests for malformed kubectl output
- No tests for different kubectl versions
- No tests for edge cases (empty lists, null values)

### 4. Collectors (`collectors/`)
- No tests for timeout handling
- No tests for RBAC error scenarios
- No tests for retry logic
- No unit tests with mocked kubectl

### 5. Models (`models.py`)
- No validation of Pydantic model constraints
- No tests for property accessors
- No tests for serialization/deserialization

---

## Testing Roadmap

### Phase 1: Foundation (Target: Q1 2024)
**Goal**: 50% code coverage

- [ ] Create `tests/` directory structure
- [ ] Add pytest configuration
- [ ] Add conftest.py with fixtures
- [ ] Create mock kubectl responses
- [ ] Unit tests for scoring engine (20 tests minimum)
- [ ] Unit tests for graph builder (15 tests minimum)
- [ ] Unit tests for models (10 tests minimum)
- [ ] Set up GitHub Actions CI

**Timeline**: 2-3 weeks
**Owner**: Community contributions welcome

### Phase 2: Expansion (Target: Q2 2024)
**Goal**: 70% code coverage

- [ ] Unit tests for all collectors
- [ ] Unit tests for all parsers
- [ ] Unit tests for renderers
- [ ] Integration tests with pytest
- [ ] Property-based tests for scoring
- [ ] Snapshot tests for ASCII rendering

**Timeline**: 4-6 weeks

### Phase 3: Excellence (Target: Q3 2024)
**Goal**: 90% code coverage

- [ ] Edge case tests for all modules
- [ ] Performance benchmarking tests
- [ ] Load tests (1k, 10k, 100k resources)
- [ ] Chaos testing (network failures, timeouts)
- [ ] Mutation testing
- [ ] Security testing (input injection, etc.)

**Timeline**: Ongoing

---

## How to Run Tests

### Integration Tests (Current)
```bash
# Requires: minikube or k8s cluster
./test.sh

# Or setup minikube first:
./test-setup-minikube.sh
./test.sh
```

### Unit Tests (Future)
```bash
# Once implemented:
pytest tests/unit/           # Unit tests only
pytest tests/integration/    # Integration tests
pytest --cov=kubectl_smart   # With coverage
pytest -v                    # Verbose output
```

---

## Contributing Tests

We **desperately need** test contributions! Even small tests help.

### Easy First Tests (Good for Contributors)

1. **Test scoring thresholds**:
```python
def test_critical_severity_threshold():
    issue = Issue(score=95.0, ...)
    assert issue.severity == IssueSeverity.CRITICAL

def test_warning_severity_threshold():
    issue = Issue(score=75.0, ...)
    assert issue.severity == IssueSeverity.WARNING
```

2. **Test model validation**:
```python
def test_resource_record_full_name():
    resource = ResourceRecord(
        kind=ResourceKind.POD,
        name="test-pod",
        namespace="default",
        uid="123"
    )
    assert resource.full_name == "Pod/default/test-pod"
```

3. **Test graph operations**:
```python
def test_graph_builder_add_vertex():
    builder = GraphBuilder()
    resource = create_test_resource()
    builder._add_vertex(resource)
    assert resource.uid in builder.uid_to_vertex
```

### Test Writing Guidelines

1. **One assertion per test** (when possible)
2. **Descriptive test names**: `test_scoring_engine_returns_zero_for_healthy_pod`
3. **Use fixtures** for common setup
4. **Mock external dependencies** (kubectl calls)
5. **Test both happy path and error cases**
6. **Add docstrings** explaining what is tested

### File Structure
```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── unit/
│   ├── test_scoring.py      # Scoring engine tests
│   ├── test_graph.py        # Graph builder tests
│   ├── test_models.py       # Pydantic model tests
│   ├── test_collectors.py   # Collector tests (mocked)
│   └── test_parsers.py      # Parser tests
├── integration/
│   ├── test_diag_command.py # End-to-end diag tests
│   ├── test_graph_command.py
│   └── test_top_command.py
└── fixtures/
    ├── sample_pods.json
    ├── sample_events.json
    └── sample_deployments.json
```

---

## Why Integration Tests Aren't Enough

**Integration tests** (like our current bash tests) are valuable but insufficient:

✅ **Pros:**
- Test real-world scenarios
- Catch integration bugs
- Validate end-to-end workflows
- Test against actual kubectl

❌ **Cons:**
- **Slow**: Require full cluster (seconds per test)
- **Flaky**: Network issues, cluster state
- **Hard to debug**: Many components involved
- **Limited coverage**: Can't test all code paths
- **Can't test edge cases**: Hard to create weird cluster states

**Unit tests** complement integration tests:

✅ **Pros:**
- **Fast**: Milliseconds per test
- **Reliable**: No external dependencies
- **Precise**: Test one thing at a time
- **Easy to debug**: Isolated failures
- **High coverage**: Test all code paths

We need **both**.

---

## Test Quality Standards

### Minimum Requirements for PR Approval

1. **No regressions**: All existing integration tests must pass
2. **New features**: Must include tests (unit or integration)
3. **Bug fixes**: Must include regression test
4. **Refactoring**: Must not decrease coverage

### Code Coverage Goals

- **Immediate**: Get infrastructure in place
- **3 months**: 50% coverage
- **6 months**: 70% coverage
- **12 months**: 90% coverage

We will track progress publicly in GitHub issues.

---

## Frequently Asked Questions

### Q: Why ship without unit tests?

**A**: This is a young project built to validate the concept and architecture. We prioritized:
1. Core functionality
2. Real-world testing (integration)
3. Documentation

Now that the concept is proven, we're investing in unit tests. We're honest about this trade-off.

### Q: Is it safe to use without tests?

**A**: For production-critical workloads: **No, not yet.**

For:
- Learning/development environments: ✅ Yes
- Read-only analysis: ✅ Yes (it never modifies clusters)
- Non-critical clusters: ✅ Probably
- Production debugging: ⚠️ Use with caution
- Production automation: ❌ Wait for 1.0 with full tests

### Q: How can I help?

**A**:
1. Write tests! Even one test helps.
2. Report bugs (helps us write tests)
3. Review test PRs
4. Share edge cases we should test

### Q: When will you have 90% coverage?

**A**: Realistically, 12-18 months if community helps. We're a small team and won't rush it.

---

## Comparison to pyproject.toml

Our `pyproject.toml` previously claimed:
```toml
[tool.pytest.ini_options]
addopts = ["--cov-fail-under=90"]
```

**This was aspirational, not reality.** We've updated the configuration to reflect current state and removed the coverage requirement until we actually have the tests.

---

## Conclusion

We believe **honesty builds trust**.

Yes, we have a testing gap. Yes, we're working on it. Yes, we need help.

But we also have:
- ✅ Solid architecture
- ✅ Real-world validation (integration tests)
- ✅ Read-only safety (never modifies clusters)
- ✅ Active development
- ✅ Clear roadmap

If you need battle-tested, 90%-covered code, wait for our 1.0 release or contribute tests.

If you can accept a well-architected beta with honest communication, we'd love your feedback.

---

**Last updated**: 2024-11-06
**Test coverage**: ~15% (integration only)
**Next milestone**: Create tests/ directory + 10 unit tests
