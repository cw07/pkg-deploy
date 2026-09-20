# pkg-deploy

Modern Python Package Deployment Tool

## What is it

`pkg-deploy` is a comprehensive Python package deployment tool that streamlines the process of building, versioning, and publishing Python packages to PyPI and private repositories. It supports both standard and Cython builds, automatic version management, and seamless Git integration.

## Features

- **Automatic Version Management**: Support for semantic versioning with patch, minor, major, alpha, beta, and release candidate bumps
- **Flexible Build System**: Standard Python builds and optimized Cython compilation
- **Code Minification**: Optionally shrink the code before Cython compilation
- **Source Leak Check**: Cython wheels are rejected before upload if any `.py` or intermediate C source slipped in
- **Multiple Repository Support**: Deploy to PyPI, private Nexus repositories, and custom package indexes
- **Git Integration**: Automatic tagging and commit management
- **Environment Detection**: Native support for both pip and uv virtual environments
- **Dry Run Mode**: Build the wheel without publishing it, bumping the version, or touching Git
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

`pyproject.toml` is **required**. `pkg-deploy` refuses to start without one, and it must declare
`[project].name` and `[project].version` — the version is read from and written back to this file
only, so a `setup.py` cannot stand in for it.

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

# Optional: extra files to bump alongside pyproject.toml (otherwise only pyproject.toml changes)
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

Both the `src` layout and the flat layout (package directly under the project root, no
`src/`) are supported, including for Cython builds. `pkg-deploy` tells them apart by whether the
resolved directory contains an `__init__.py`: if it does, it is the package itself and its parent
is treated as the source root; otherwise it is a container such as `src/`. The resolved directory
must be inside the project directory.

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

# Pre-release cycle. From a final release, alpha/beta/rc start a cycle on the
# NEXT patch version, because PEP 440 sorts 1.2.4a1 before 1.2.4 and a pre-release
# published after its final would be invisible to pip.
pkg-deploy --repository-name pypi --version-type alpha  # 1.2.4    -> 1.2.5a1
pkg-deploy --repository-name pypi --version-type alpha  # 1.2.5a1  -> 1.2.5a2
pkg-deploy --repository-name pypi --version-type beta   # 1.2.5a2  -> 1.2.5b1
pkg-deploy --repository-name pypi --version-type rc     # 1.2.5b1  -> 1.2.5rc1
pkg-deploy --repository-name pypi                       # 1.2.5rc1 -> 1.2.5  (patch finalises)
```

Rules for pre-releases:

- Stages only move forward (`alpha` → `beta` → `rc`); any can be skipped, none can be revisited.
  `1.2.5rc1 --version-type alpha` is refused — use `--new-version` to force a value.
- `patch` (the default) on a pre-release drops the suffix: `1.2.5a1`, `1.2.5b1` and `1.2.5rc1`
  all finalise to `1.2.5`.
- `minor` / `major` on a pre-release abandon the cycle: `1.2.5rc1` → `1.3.0` / `2.0.0`.
- A pre-release of the next *minor* (`1.3.0a1`) is not inferred — pass it explicitly with
  `--new-version 1.3.0a1`.

### Cython Builds

```bash
# Build with Cython optimization
pkg-deploy --repository-name pypi --version-type patch --cython

# Cython build for private repository
pkg-deploy --repository-url https://nexus.example.com/repository/pypi-internal/ \
           --username user_name --password secret --cython

# Cython build with code minification
pkg-deploy --repository-name pypi --version-type patch --cython --minify
```

#### How `setup.py` is handled

A Cython build needs a `setup.py`. `pkg-deploy` decides what to do based on what it finds in
the project directory:

| Situation | Behaviour |
|---|---|
| No `setup.py` | One is generated for the build and deleted again during cleanup |
| `setup.py` exists and contains `cythonize` | Yours is used as-is and never overwritten |
| `setup.py` exists without `cythonize` | The build stops with `FileExistsError` — back it up or migrate it to `pyproject.toml` |

`pkg-deploy` also rewrites `[build-system]` in `pyproject.toml` for the duration of the build
(adding `setuptools`/`Cython` to `requires` and forcing `build-backend` to
`setuptools.build_meta`), then restores it afterwards. Any version bump you asked for survives
the restore; only the injected build-system entries are removed.

The Cython version actually used comes from your `[build-system].requires`. If you want a
specific one, pin it there — the `setup_requires` line in the generated `setup.py` is a legacy
field and does not control it.

### Multiple Python Version Builds with cibuildwheel

`pkg-deploy` can hand the build to `cibuildwheel`, which produces one wheel per Python version
listed in your `[tool.cibuildwheel]` configuration in a single run.

cibuildwheel builds for the operating system it is running on: on Linux it produces manylinux
wheels (inside Docker), on macOS macOS wheels, on Windows Windows wheels. To cover several
platforms, run `pkg-deploy --cibuildwheel` once on each — it does not cross-compile.

#### Benefits
- **Multiple Python Versions**: One run yields a wheel for every version in `build = "cp38-* cp39-* ..."`
- **Proper Platform Tags**: Wheels are tagged and (on Linux) audited for manylinux compatibility

#### Requirements
- **Docker (Linux only)**: Docker must be installed and running when building on Linux
- **cibuildwheel**: Installed together with `pkg-deploy`
- **Sufficient disk space**: One build environment per Python version

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
# Cython build for every configured Python version
pkg-deploy --repository-name pypi --version-type patch --cython --cibuildwheel

# Same, to a private repository
pkg-deploy --repository-url https://nexus.example.com/repository/pypi-internal/ \
           --username admin --password secret --cython --cibuildwheel

# Dry run to check the cibuildwheel configuration
pkg-deploy --repository-name pypi --cython --cibuildwheel --dry-run
```

#### Limitations
- **Build Time**: Each Python version is compiled separately, so runs take proportionally longer
- **Docker Dependency**: Linux builds require Docker to be installed and running
- **One platform per run**: Wheels for other operating systems need a run on that system

### Advanced Options

```bash
# Custom project directory
pkg-deploy --project-dir /path/to/project --repository-name pypi

# Custom package directory
pkg-deploy --package-dir /path/to/package --repository-name pypi

# Publish without recording the release in Git (version bump is reverted)
pkg-deploy --repository-name pypi --new-version 1.2.3 --discard-version-bump

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
- `--new-version, -v`: Specify exact version number (overrides version-type). Must match `MAJOR.MINOR.PATCH` with an optional `aN` / `bN` / `rcN` suffix — `1.2`, `1.2.3.post1` and `1.2.3dev1` are rejected
- `--cython, -c`: Enable Cython compilation for performance
- `--minify, -m`: Minify the code before compilation to reduce its size. Must be used together with `--cython`
- `--cibuildwheel`: Build with cibuildwheel — one wheel per configured Python version, for the platform you run it on (requires Docker on Linux)
- `--repository-name, -rn`: Repository name from .pypirc configuration (e.g., 'pypi', 'testpypi')
- `--repository-url, -ru`: Repository upload URL (prompts for username/password if not in .pypirc)
- `--username, -u`: Authentication username (optional if configured in .pypirc)
- `--password, -p`: Authentication password/token (optional if configured in .pypirc)
- `--discard-version-bump`: Leave the repository untouched — no bump commit, no tag, no push, and the version bump written to `pyproject.toml` is reverted after a successful upload. The published version is then recorded nowhere in the repo, so the next deploy resolves to that same version again and the upload clashes; pair it with `--new-version`
- `--skip-git-status-check`: Skip Git status validation before deployment
- `--dry-run`: Build the wheel and log what would be uploaded, without publishing it, bumping the version, or touching Git. The build itself really runs, so `dist/` and `build/` are created and then cleaned up
- `--verbose, -V`: Debug logging, including the full output of the build tool (which packages the isolated build environment installed, which modules were cythonized, compiler warnings)

## Environment Support

### UV Virtual Environments

`pkg-deploy` detects a uv-managed environment by looking for a `uv = ...` marker in the
`pyvenv.cfg` of the active interpreter. When it finds one it builds with `uv build --wheel`
(installing `uv` first if it is missing); otherwise it falls back to `python -m build --wheel`.
Passing `--cibuildwheel` overrides both and runs `cibuildwheel` instead.

Either way the build runs in an isolated environment that installs your
`[build-system].requires` fresh, so that is where build-time pins such as `Cython>=3.2` take
effect. Note that uv caches resolutions — run `uv cache clean` if you need to be certain you
picked up the newest matching release.

## Security Considerations

### API Tokens (Recommended)

For PyPI, use API tokens instead of passwords:

1. Generate token at https://pypi.org/manage/account/token/
2. Use `__token__` as username
3. Use the generated token as password

### Credential Storage

- Store credentials in `.pypirc` for reusability
- Credentials are handed to twine through the `TWINE_USERNAME` / `TWINE_PASSWORD` environment
  variables of the child process, never on its command line, so they do not show up in `ps` or
  in any logged command
- Leave `--username` / `--password` off the command line and let `pkg-deploy` prompt for them
  instead — the prompt uses `getpass`, so nothing is echoed or kept in your shell history

## Troubleshooting

### Common Issues

**Git Repository Not Clean**
```
Error: Git repo is NOT clean
```
Solution: Commit or stash your changes before deployment, or use `--skip-git-status-check`.

**Missing Dependencies**
```
Error: Missing required packages: build, twine
```
Solution: Install the missing packages. `build`, `twine` and `tomlkit` are always
required; `--cython` additionally requires `Cython`.

**Cython Build Conflicts**
```
Error: Cannot build Cython code: setup.py already exists
```
Solution: Back up the existing `setup.py`, add a `cythonize` call to it so `pkg-deploy` uses it
as-is, or migrate its configuration to `pyproject.toml`. See
[How `setup.py` is handled](#how-setuppy-is-handled).

**Source Leak Detected**
```
ValueError: Source leak detected in built wheel(s) - refusing to upload.
```
Solution: The listed files should have been compiled but were not. Check that every directory
holding those modules has an `__init__.py`.

**Contradictory Package Directory**
```
ValueError: Package directory from toml are not the same: ['src', 'lib']
```
Solution: Make `tool.setuptools.packages.find.where` and `tool.setuptools.package-dir` point at
the same directory, or pass `--package-dir` to override both.

**Build Failures**
```
ValueError: Cython build failed,
stdout: ...
stderr: ...
```
Solution: `pkg-deploy` reports the underlying build tool's output verbatim — read the `stderr`
section first. For `--cibuildwheel` on Linux, check that Docker is installed and running,
verify your `[tool.cibuildwheel]` configuration, and make sure there is enough disk space.
`pkg-deploy` itself does not check for Docker, so a missing daemon surfaces as a cibuildwheel
error inside this output.

**Authentication Failures**
```
Error: 403 Forbidden
```
Solution: Verify credentials, or use API tokens for PyPI. Omitting `--username` / `--password`
makes `pkg-deploy` prompt for them interactively.

### Debug Mode

Enable verbose logging for detailed troubleshooting:

```bash
pkg-deploy --repository-name pypi --verbose --dry-run
```

---

**pkg-deploy** - Streamlining Python package deployment since 2025.