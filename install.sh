#!/bin/bash
# Installation script for kubectl-smart using uv (idempotent)

set -euo pipefail

echo "🚀 Installing kubectl-smart"
echo "================================================"

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" ]]; then
    echo "❌ Error: pyproject.toml not found. Run this script from the kubectl-smart directory."
    exit 1
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv (Python package manager)..."
    curl -fsSL https://astral.sh/uv/install.sh | sh
    
    # Source cargo env to make uv available immediately
    if [[ -f "$HOME/.cargo/env" ]]; then
        source "$HOME/.cargo/env"
    fi
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    
    # Check if uv is now available
    if ! command -v uv &> /dev/null; then
        echo "❌ Error: Failed to install uv. Please install manually:"
        echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "   Then restart your terminal and run this script again."
        exit 1
    fi
    echo "✅ uv installed successfully"
else
    echo "✅ uv package manager ready"
fi

# Ensure PATH includes local bin
export PATH="$HOME/.local/bin:$PATH"

# Report any existing binary, then let uv replace the tool environment.
if command -v kubectl-smart &> /dev/null; then
    echo "🔄 Found existing kubectl-smart at $(command -v kubectl-smart); reinstalling from current code..."
fi

# Install kubectl-smart globally using uv
echo "📦 Installing kubectl-smart globally from current code..."
uv tool install . --force --reinstall

# Verify installation
if command -v kubectl-smart &> /dev/null; then
    echo "✅ Installation successful!"
    
    # Test basic functionality
    echo ""
    echo "🧪 Testing installation..."
    if version_output=$(kubectl-smart --version 2>&1); then
        echo "✅ kubectl-smart is working correctly"
        echo "$version_output"
    else
        echo "⚠️  kubectl-smart installed but version check failed"
    fi
else
    echo "❌ Installation failed - kubectl-smart not found in PATH"
    echo "💡 You may need to add ~/.local/bin to your PATH:"
    echo "   echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
    echo "   echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
    exit 1
fi

echo ""
echo "🎯 kubectl-smart is now available globally:"
echo "   kubectl-smart diag pod <name>"
echo "   kubectl-smart graph pod <name> --upstream" 
echo "   kubectl-smart top <namespace>"
echo "   kubectl-smart --help"
echo ""
echo "📚 Ready to debug Kubernetes with intelligence! 🚀"

# Add PATH suggestion if not already in shell config
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo "💡 To ensure kubectl-smart is always available, add this to your shell config:"
    echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
