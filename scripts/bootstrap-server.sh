#!/bin/bash

# Exit on error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo_error "Please do not run this script as root. Run as a regular user with sudo privileges."
    exit 1
fi

# Update system
echo_info "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install essential dependencies
echo_info "Installing essential dependencies..."
sudo apt install -y curl wget git unzip ca-certificates gnupg software-properties-common

# ============================================================================
# GOLANG
# ============================================================================
install_golang() {
    echo_info "Installing Golang..."

    GO_VERSION="1.26.0"

    if command -v go &> /dev/null; then
        echo_warn "Golang is already installed: $(go version)"
    else
        wget -q "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz"
        sudo rm -rf /usr/local/go
        sudo tar -C /usr/local -xzf "go${GO_VERSION}.linux-amd64.tar.gz"
        rm "go${GO_VERSION}.linux-amd64.tar.gz"

        # Add to PATH if not already present
        if ! grep -q '/usr/local/go/bin' ~/.bashrc; then
            echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
        fi
        export PATH=$PATH:/usr/local/go/bin

        echo_info "Golang ${GO_VERSION} installed successfully!"
    fi
}

# ============================================================================
# GOLANGCI-LINT
# ============================================================================
install_golangci_lint() {
    echo_info "Installing golangci-lint..."

    if command -v golangci-lint &> /dev/null; then
        echo_warn "golangci-lint is already installed: $(golangci-lint --version)"
    else
        # Install golangci-lint using the official install script
        curl -sSfL https://golangci-lint.run/install.sh | sh -s -- -b $(go env GOPATH)/bin v2.9.0

        # Add GOPATH/bin to PATH if not already present
        GOPATH=$(go env GOPATH)
        if ! grep -q "${GOPATH}/bin" ~/.bashrc 2>/dev/null; then
            echo "export PATH=\$PATH:${GOPATH}/bin" >> ~/.bashrc
        fi
        export PATH=$PATH:${GOPATH}/bin

        echo_info "golangci-lint installed successfully!"
    fi
}

# ============================================================================
# NODE.JS
# ============================================================================
install_nodejs() {
    echo_info "Installing Node.js..."

    if command -v node &> /dev/null; then
        echo_warn "Node.js is already installed: $(node --version)"
    else
        # Download and install nvm:
        curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash

        # in lieu of restarting the shell
        \. "$HOME/.nvm/nvm.sh"

        # Download and install Node.js:
        nvm install 24

        echo_info "Node.js $(node --version) installed successfully!"
    fi
}

# ============================================================================
# BUN
# ============================================================================
install_bun() {
    echo_info "Installing Bun..."

    if command -v bun &> /dev/null; then
        echo_warn "Bun is already installed: $(bun --version)"
    else
        curl -fsSL https://bun.sh/install | bash

        # Add to PATH for current session
        export BUN_INSTALL="$HOME/.bun"
        export PATH="$BUN_INSTALL/bin:$PATH"

        echo_info "Bun installed successfully!"
    fi
}

# ============================================================================
# GITHUB CLI
# ============================================================================
install_gh() {
    echo_info "Installing GitHub CLI..."

    if command -v gh &> /dev/null; then
        echo_warn "GitHub CLI is already installed: $(gh --version)"
    else
        (type -p wget >/dev/null || (sudo apt update && sudo apt install wget -y)) \
	&& sudo mkdir -p -m 755 /etc/apt/keyrings \
	&& out=$(mktemp) && wget -nv -O$out https://cli.github.com/packages/githubcli-archive-keyring.gpg \
	&& cat $out | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
	&& sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
	&& sudo mkdir -p -m 755 /etc/apt/sources.list.d \
	&& echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
	&& sudo apt update \
	&& sudo apt install gh -y

        echo_info "GitHub CLI installed successfully!"
    fi
}

# ============================================================================
# TAILSCALE
# ============================================================================
install_tailscale() {
    echo_info "Installing Tailscale..."

    if command -v tailscale &> /dev/null; then
        echo_warn "Tailscale is already installed: $(tailscale version)"
    else
        curl -fsSL https://tailscale.com/install.sh | sh

        echo_info "Tailscale installed successfully!"
        echo_warn "Run 'sudo tailscale up' to connect to your tailnet"
    fi
}

# ============================================================================
# OPENCODE CLI
# ============================================================================
install_opencode() {
    echo_info "Installing OpenCode CLI..."

    if command -v opencode &> /dev/null; then
        echo_warn "OpenCode CLI is already installed"
    else
        curl -fsSL https://opencode.ai/install | bash

        # Add to PATH for current session
        export PATH="$HOME/.opencode/bin:$PATH"

        echo_info "OpenCode CLI installed successfully!"
    fi
}

# ============================================================================
# CODEX CLI
# ============================================================================
install_codex() {
    echo_info "Installing Codex CLI..."

    if command -v codex &> /dev/null; then
        echo_warn "Codex CLI is already installed: $(codex --version)"
    else
        npm install -g @openai/codex

        echo_info "Codex CLI installed successfully!"
        echo_warn "Set your OPENAI_API_KEY environment variable to use Codex"
    fi
}

# ============================================================================
# CLAUDE CODE CLI
# ============================================================================
install_claude_code() {
    echo_info "Installing Claude Code CLI..."

    if command -v claude &> /dev/null; then
        echo_warn "Claude Code CLI is already installed: $(claude --version)"
    else
        curl -fsSL https://claude.ai/install.sh | bash

        # Add to PATH for current session
        export PATH="$HOME/.local/bin:$PATH"

        echo_info "Claude Code CLI installed successfully!"
    fi
}

# ============================================================================
# DOCKER
# ============================================================================
install_docker() {
    echo_info "Installing Docker..."
    
    if command -v docker &> /dev/null; then
        echo_warn "Docker is already installed: $(docker --version)"
    else
        # Install dependencies
        sudo apt install -y apt-transport-https
        
        # Add Docker's official GPG key
        sudo install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
            sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        sudo chmod a+r /etc/apt/keyrings/docker.gpg
        
        # Set up Docker repository
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
            https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
            sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        
        # Install Docker
        sudo apt update
        sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        
        # Add user to docker group
        sudo usermod -aG docker "$USER"
        
        # Enable Docker service
        sudo systemctl enable docker
        sudo systemctl start docker
        
        echo_info "Docker installed successfully!"
        echo_warn "You may need to log out and back in for docker group changes to take effect"
    fi
}

# ============================================================================
# LAZYDOCKER
# ============================================================================
install_lazydocker() {
    echo_info "Installing LazyDocker..."

    if command -v lazydocker &> /dev/null; then
        echo_warn "LazyDocker is already installed"
    else
        go install github.com/jesseduffield/lazydocker@latest

        echo_info "LazyDocker installed successfully!"
    fi
}

# ============================================================================
# LAZYGIT
# ============================================================================
install_lazygit() {
    echo_info "Installing LazyGit..."

    if command -v lazygit &> /dev/null; then
        echo_warn "LazyGit is already installed: $(lazygit --version)"
    else
        go install github.com/jesseduffield/lazygit@latest

        echo_info "LazyGit ${LAZYGIT_VERSION} installed successfully!"
    fi
}

# ============================================================================
# TMUX
# ============================================================================
install_tmux() {
    echo_info "Installing tmux..."

    if command -v tmux &> /dev/null; then
        echo_warn "tmux is already installed: $(tmux -V)"
    else
        sudo apt install -y tmux

        echo_info "tmux installed successfully!"
    fi
}

# ============================================================================
# HTOP
# ============================================================================
install_htop() {
    echo_info "Installing htop..."

    if command -v htop &> /dev/null; then
        echo_warn "htop is already installed: $(htop --version)"
    else
        sudo apt install -y htop

        echo_info "htop installed successfully!"
    fi
}

# ============================================================================
# MAIN INSTALLATION
# ============================================================================
main() {
    echo_info "Starting installation of development tools..."
    echo ""

    install_golang
    echo ""

    install_golangci_lint
    echo ""

    install_nodejs
    echo ""

    install_bun
    echo ""

    install_gh
    echo ""

    install_tailscale
    echo ""

    install_opencode
    echo ""

    install_codex
    echo ""

    install_claude_code
    echo ""

    install_docker
    echo ""

    install_lazydocker
    echo ""

    install_lazygit
    echo ""

    install_tmux
    echo ""

    install_htop
    echo ""

    echo_info "All installations complete!"
    echo ""
    echo_warn "IMPORTANT: Please restart your terminal or run 'source ~/.bashrc' to update your PATH"
    echo ""
    echo_info "Installed tools:"
    echo "  - Golang:        $(go version 2>/dev/null || echo 'restart terminal')"
    echo "  - golangci-lint: $(golangci-lint --version 2>/dev/null || echo 'restart terminal')"
    echo "  - Node.js:       $(node --version 2>/dev/null || echo 'restart terminal')"
    echo "  - Bun:           $(bun --version 2>/dev/null || echo 'restart terminal')"
    echo "  - GitHub CLI:    $(gh --version 2>/dev/null | head -1 || echo 'restart terminal')"
    echo "  - Tailscale:     $(tailscale version 2>/dev/null | head -1 || echo 'restart terminal')"
    echo "  - OpenCode:      $(opencode --version 2>/dev/null || echo 'restart terminal')"
    echo "  - Codex CLI:     $(codex --version 2>/dev/null || echo 'restart terminal')"
    echo "  - Claude Code:   $(claude --version 2>/dev/null || echo 'restart terminal')"
    echo "  - Docker:        $(docker --version 2>/dev/null || echo 'restart terminal')"
    echo "  - LazyDocker:    $(lazydocker --version 2>/dev/null || echo 'restart terminal')"
    echo "  - LazyGit:       $(lazygit --version 2>/dev/null || echo 'restart terminal')"
    echo "  - tmux:          $(tmux -V 2>/dev/null || echo 'restart terminal')"
    echo "  - htop:          $(htop --version 2>/dev/null || echo 'restart terminal')"
    echo ""
    echo_warn "Post-installation steps:"
    echo "  1. For Docker:        Log out and back in for docker group to take effect"
    echo "  2. For Tailscale:     Run 'sudo tailscale up' to connect"
    echo "  3. For Codex CLI:     Set OPENAI_API_KEY environment variable"
    echo "  4. For Claude Code:   Run 'claude' to authenticate"
    echo "  5. For GitHub CLI:    Run 'gh auth login' to authenticate"
}

main "$@"
