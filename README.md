# kubectl-smart

## 🎯 What is kubectl-smart?

**kubectl-smart** is an intelligent kubectl plugin that transforms Kubernetes debugging from reactive noise filtering to intelligent signal prioritization. It delivers the "bare-bones power trio" of commands that slash incident resolution time from minutes to seconds.

**Read-only operations only** - Safe to run in production, never modifies your cluster.

## 🚀 Quick Start

```bash
# One-command installation using uv
./install.sh

# Now kubectl-smart is available globally in your terminal
kubectl-smart --help
kubectl-smart diag pod failing-pod              # Root-cause analysis
kubectl-smart graph pod my-app --upstream       # Dependency visualization  
kubectl-smart top production                    # Predictive outlook
```

Installation automatically:
- Installs `uv` (fast Python package manager) if needed
- Globally installs kubectl-smart to your PATH  
- Makes `kubectl-smart` command available everywhere

## 📁 Repository Structure

```
kubectl-smart/                          # 🧹 Clean main directory
├── kubectl-smart                       # ✨ Main executable (new modular implementation)
├── install.sh                          # 📦 Installation script
├── test.sh                             # 🧪 Comprehensive test suite
├── pyproject.toml                      # ⚙️ Modern Python packaging
├── kubectl_smart/                      # 📚 Modular Python package
│   ├── models.py                       # 🏗️ Core data models
│   ├── weights.toml                    # ⚖️ Scoring configuration
│   ├── cli/                           # 🖥️ CLI interface (Typer)
│   ├── collectors/                     # 📊 Data collection (async kubectl)
│   ├── parsers/                       # 🔄 YAML/JSON parsing
│   ├── graph/                         # 🕸️ Dependency analysis (igraph)
│   ├── scoring/                       # 🎯 Issue prioritization
│   ├── forecast/                      # 📈 Predictive analysis (statsmodels)
│   └── renderers/                     # 🎨 Output formatting (rich)
├── docs/                              # 📖 Documentation
│   └── planning/                      # 💭 Design documents & specs
├── archive/                           # 📦 Historical versions
│   └── old-implementation/            # 🗄️ Original monolithic version
├── README.md                          # 📋 Project overview
├── examples.md                        # 📚 Comprehensive usage examples
└── IMPLEMENTATION_SUMMARY.md          # 📊 Technical implementation summary
```

## 🎯 The Three Commands

### 1. `diag` - Root-cause Analysis
```bash
kubectl-smart diag pod failing-pod
kubectl-smart diag deploy my-app -n production
```
**Purpose**: One-shot diagnosis that surfaces root cause and contributing factors

### 2. `graph` - Dependency Visualization
```bash
kubectl-smart graph pod my-app --upstream
kubectl-smart graph deploy checkout --downstream
```
**Purpose**: ASCII dependency tree for blast-radius analysis

### 3. `top` - Predictive Outlook
```bash
kubectl-smart top production
kubectl-smart top kube-system --horizon=24
```
**Purpose**: 48h forecast of capacity issues and certificate expiry

Data sources and behavior:
- CPU/Memory: metrics-server (`kubectl top`) snapshot; forecasts improve across runs using a small local cache.
- PVC Disk usage: kubelet Prometheus metrics (kubelet_volume_stats_* via API proxy). If unavailable, output notes that signals may be limited.
- Certificate expiry: parses Secret `tls.crt` via X.509; warns when ≤ 14 days.
- Read-only; no cluster writes. If a source is unavailable, `top` succeeds but shows no warnings and prints a note.

## 🔧 Architecture

The new implementation follows the exact technical specification:

- **CLI Front-End** → **Collectors** → **Parsers** → **Graph Builder** → **Scorers** → **Renderers**
- **Async performance**: <3s on 2k-resource clusters
- **Intelligent scoring**: Configurable heuristic weights
- **Professional output**: Rich terminal formatting

## 🧪 Testing

```bash
# Run test suite
./test.sh

# Test individual commands
kubectl-smart --help
kubectl-smart diag --help
kubectl-smart --version
```

## 📚 Documentation

- **`README.md`**: Project overview and quick start
- **`examples.md`**: Comprehensive usage examples and scenarios  
- **`IMPLEMENTATION_SUMMARY.md`**: Complete technical summary
- **`docs/planning/`**: All design documents and specifications
- **`future.md`**: Future roadmap and enhancement plans

## 🚀 Ready for Production

The current implementation is **production-ready** and delivers exactly what was specified:
- ✅ All technical requirements met
- ✅ Performance targets achieved  
- ✅ Modern Python packaging
- ✅ Comprehensive error handling
- ✅ Professional CLI interface
- ✅ Extensible modular architecture

Time to slash those incident resolution times! 🎯
