# pkg-deploy

Modern Python Package Deployment Tool

## What is it

`pkg-deploy` is a comprehensive Python package deployment tool that streamlines the process of building, versioning, and publishing Python packages to PyPI and private repositories. It supports both standard and Cython builds, automatic version management, and seamless Git integration.

## Features

- **Automatic Version Management**: Support for semantic versioning with patch, minor, major, alpha, beta, and release candidate bumps
- **Flexible Build System**: Standard Python builds and optimized Cython compilation
- **Multiple Repository Support**: Deploy to PyPI, private Nexus repositories, and custom package indexes
- **Git Integration**: Automatic tagging and commit management
- **Environment Detection**: Native support for both pip and uv virtual environments
- **Dry Run Mode**: Test deployments without making actual changes
- **Interactive Authentication**: Secure credential input with API token support
- **Automatic Cleanup**: Clean removal of build artifacts after deployment

## Installation

### From PyPI

```bash
pip install pkg-deploy
```

## Quick Start

### Basic Usage

After installing pkg-deploy , navigate to your project directory (the folder containing your pyproject.toml ) and use the pkg-deploy command directly. 
Example project structure:

```text
my-package/
├── src/
│   └── my_package/
│       ├── __init__.py
│       └── main.py
├── pyproject.toml
└── README.md
```

#### Running the Deployment

Use the `pkg-deploy` command with your desired arguments:

```bash
# Deploy with patch version bump to PyPI
pkg-deploy --repository-name pypi --version-type patch

# Deploy to private repository with minor version bump
pkg-deploy --repository-url https://nexus.example.com/repository/pypi-internal/ \
           --username admin --password secret --version-type minor

# Dry run to test configuration
pkg-deploy --repository-name pypi --version-type patch --dry-run
```
## Configuration

### pyproject.toml

Ensure your `pyproject.toml` includes the required project metadata:

```toml
[build-system]
requires = ["setuptools>=70"]
build-backend = "setuptools.build_meta"

[project]
name = "your-package-name"
version = "1.0.0"
description = "Your package description"
requires-python = ">=3.10"
authors = [
    { name = "Your Name", email = "your.email@example.com" },
]
readme = "README.md"
dependencies = [
    "dependency1",
    "dependency2",
]

[tool.setuptools]
package-dir = {"" = "src"}
zip-safe = false

[tool.setuptools.packages.find]
where = ["src"]

# Optional: Version bump configuration, other wise will only bump version in pyproject.toml
[[tool.bumpversion.file]]
filename = "src/your_package/__init__.py"
search = '__version__ = "{current_version}"'
replace = '__version__ = "{new_version}"'
```

### .pypirc Configuration

For repository authentication, create a `.pypirc` file in your user home directory:
- Unix/macOS: `~/.pypirc`
- Windows: `C:\Users\username\.pypirc`

```ini
[distutils]
index-servers =
    pypi
    private-repo

[pypi]
repository = https://upload.pypi.org/legacy/
username = __token__
password = pypi-your-api-token-here

[private-repo]
repository = https://nexus.example.com/repository/pypi-internal/
username = your-username
password = your-password
```

## Usage Examples

### Version Management

```bash
# Patch version bump (1.0.0 -> 1.0.1)
pkg-deploy --repository-name pypi --version-type patch

# Minor version bump (1.0.1 -> 1.1.0)
pkg-deploy --repository-name pypi --version-type minor

# Major version bump (1.1.0 -> 2.0.0)
pkg-deploy --repository-name pypi --version-type major

# Use specific version
pkg-deploy --repository-name pypi --new-version 2.1.0

# Pre-release versions
pkg-deploy --repository-name pypi --version-type alpha  # 1.0.0a1
pkg-deploy --repository-name pypi --version-type beta   # 1.0.0b1
pkg-deploy --repository-name pypi --version-type rc     # 1.0.0rc1
```

### Cython Builds

```bash
# Build with Cython optimization
pkg-deploy --repository-name pypi --version-type patch --cython

# Cython build for private repository
pkg-deploy --repository-url https://nexus.example.com/repository/pypi-internal/ \
           --username admin --password secret --cython
```

### Advanced Options

```bash
# Custom project directory
pkg-deploy --project-dir /path/to/project --repository-name pypi

# Skip Git operations
pkg-deploy --repository-name pypi --skip-git-push

# Verbose logging
pkg-deploy --repository-name pypi --verbose

# Dry run with verbose output
pkg-deploy --repository-name pypi --dry-run --verbose
```

## Command Line Interface

### Arguments

- `--project-dir`: Project directory (default: current directory)
- `--version-type, -vt`: Version bump type: patch, minor, major, alpha, beta, or rc
- `--new-version, -v`: Specify exact version number (overrides version-type)
- `--cython, -c`: Enable Cython compilation for performance
- `--repository-name, -rn`: Repository name from .pypirc configuration (e.g., 'pypi', 'testpypi')
- `--repository-url, -rl`: Repository upload URL (prompts for username/password if not in .pypirc)
- `--username, -u`: Authentication username (optional if configured in .pypirc)
- `--password, -p`: Authentication password/token (optional if configured in .pypirc)
- `--skip-git-push`: Skip pushing version changes and tags to Git repository
- `--skip-git-status-check`: Skip Git status validation before deployment
- `--dry-run`: Simulate deployment without making actual changes
- `--verbose, -V`: Enable detailed logging output

## Environment Support

### UV Virtual Environments

`pkg-deploy` automatically detects and supports UV-managed virtual environments:


## Security Considerations

### API Tokens (Recommended)

For PyPI, use API tokens instead of passwords:

1. Generate token at https://pypi.org/manage/account/token/
2. Use `__token__` as username
3. Use the generated token as password

### Credential Storage

- Store credentials in `.pypirc` for reusability
- Enable interactive mode for secure input

## Troubleshooting

### Common Issues

**Git Repository Not Clean**
```
Error: Git repo is NOT clean
```
Solution: Commit or stash your changes before deployment or use `--skip-git-push`.

**Missing Dependencies**
```
Error: Missing required packages: build, twine
```
Solution: Install missing packages with `pip install build twine`.

**Cython Build Conflicts**
```
Error: Cannot build Cython code: setup.py already exists
```
Solution: Backup existing `setup.py` or migrate configuration to `pyproject.toml`.

**Authentication Failures**
```
Error: 403 Forbidden
```
Solution: Verify credentials, use API tokens for PyPI, or enable interactive mode.

### Debug Mode

Enable verbose logging for detailed troubleshooting:

```bash
pkg-deploy --repository-name pypi --verbose --dry-run
```

---

**pkg-deploy** - Streamlining Python package deployment since 2025.