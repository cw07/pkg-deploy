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

### Package Directory Resolution

`pkg-deploy` automatically resolves the package directory using the following priority:

1. **Explicit --package-dir**: If specified via command line, this path is used directly
2. **pyproject.toml Configuration**: Automatically parsed from setuptools configuration:
   - `tool.setuptools.packages.find.where` - source directory location
   - `tool.setuptools.package-dir` - package directory mapping
3. **Default Fallback**: Uses `project_dir/package_name` based on the project name

Example configurations in `pyproject.toml`:

```toml
# Standard src layout
[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

# Custom package location
[tool.setuptools]
package-dir = {"my_package" = "custom/path"}
```

> **⚠️ Important**: When package directory is configured in multiple places within `pyproject.toml` (such as both `tool.setuptools.packages.find.where` and `tool.setuptools.package-dir`), all configurations must point to the same directory. If they differ, `pkg-deploy` will raise a `ValueError` with the message "Package directory from toml are not the same".

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
           --username user_name --password secret --cython
```

### Cross-Platform Multiple Version Builds with cibuildwheel

`pkg-deploy` supports `cibuildwheel` for building wheels across multiple Python versions and platforms as specified in your `pyproject.toml` configuration.

#### Benefits
- **Cython Integration**: Build wheels for all specified versions in one run
- **Multi-Platform Support**: Automatically builds wheels for Linux, macOS, and Windows
- **Multiple Python Versions**: Builds for all Python versions specified in configuration
- **Binary Compatibility**: Creates optimized binary wheels with proper platform tags

#### Requirements
- **Docker (Linux only)**: Docker must be installed and running when building on Linux systems
- **cibuildwheel**: Automatically installed as a build dependency
- **Sufficient disk space**: Cross-platform builds require more storage

#### Configuration

Add cibuildwheel configuration to your `pyproject.toml` (Optional):

```toml
[tool.cibuildwheel]
# Specify which Python versions to build for
build = "cp38-* cp39-* cp310-* cp311-* cp312-* cp313-*"
before-build = "pip install Cython"

[tool.cibuildwheel.linux]
# Use manylinux images for better compatibility
before-all = "yum install -y gcc || apt-get update && apt-get install -y gcc"

[tool.cibuildwheel.macos]
# Ensure Cython is available for macOS builds
before-build = "pip install Cython"

[tool.cibuildwheel.windows]
# Ensure Cython is available for Windows builds
before-build = "pip install Cython"
```

#### Usage Examples

```bash
# Cross-platform Cython build with cibuildwheel
pkg-deploy --repository-name pypi --version-type patch --cython --cibuildwheel

# Deploy to private repository with cross-platform builds
pkg-deploy --repository-url https://nexus.example.com/repository/pypi-internal/ \
           --username admin --password secret --cython --cibuildwheel

# Dry run to test cross-platform build configuration
pkg-deploy --repository-name pypi --cython --cibuildwheel --dry-run
```

#### Limitations
- **Build Time**: Cross-platform builds take significantly longer than single-platform builds
- **Docker Dependency**: Linux builds require Docker to be installed and running
- **Resource Usage**: Requires more CPU, memory, and disk space during build process
- **Platform Restrictions**: Some platform-specific dependencies may not be available across all targets

### Advanced Options

```bash
# Custom project directory
pkg-deploy --project-dir /path/to/project --repository-name pypi

# Custom package directory
pkg-deploy --package-dir /path/to/package --repository-name pypi

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
- `--package-dir`: Package directory path (default: auto-resolved from pyproject.toml or project name)
- `--version-type, -vt`: Version bump type: patch, minor, major, alpha, beta, or rc
- `--new-version, -v`: Specify exact version number (overrides version-type)
- `--cython, -c`: Enable Cython compilation for performance
- `--cibuildwheel`: Use cibuildwheel for cross-platform wheel building (requires Docker on Linux)
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

**Docker Not Available (Linux)**
```
Error: Docker is required for cibuildwheel on Linux
```
Solution: Install and start Docker service, or use `--cython` without `--cibuildwheel` for local builds only.

**cibuildwheel Build Failures**
```
Error: cibuildwheel build failed
```
Solution: Check Docker is running (Linux), verify `pyproject.toml` cibuildwheel configuration, and ensure sufficient disk space.

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

Noticed that the `clibuildwheel` needs docker service in Linux to build different version

**pkg-deploy** - Streamlining Python package deployment since 2025.