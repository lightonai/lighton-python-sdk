# Contributing to LightOn Python SDK

Thank you so much for your interest in contributing to to LightOn's Python SDK! We welcome contributions of all kind, we do allow AI-generated contributions while these complies with our coding rules within `AGENTS.md` but WE DO require a human presence to answer the review.

## Checklist before submitting a PR
Here are a few requirements to ensure your contribution can be integrated swiftly:

[] **Sign the Contributor License Agreement (CLA)** -> [see details](#contributor-license-agreement-cla)
[] **Keep scope isolated,**, your changes should address 1 specific problem at a time
[] **Ensure your PR passes all checks:**
  [] Unit Tests -> `make test`
  [] Linting/Formatting -> `make lint`
  [] Type Checking -> `make type-check`
[] **Add testing**, you should at least add 1 test

## Contributor License Agreement (CLA)
Before contributing code to LightOn Python SDK, you must sign our Contributor License Agreement (CLA). This is a legal requirement for all contributions to be merged into the main repository.

Important: We strongly recommend reviewing and signing the CLA before starting work on your contribution to avoid any delays in the PR process.

## Quickstart
### 1. Setup your local development environment
```
# Fork the repository on GitHub (click the Fork button at https://github.com/lightonai/lighton-python-sdk)
# Then clone your fork locally
git clone https://github.com/YOUR_USERNAME/lighton-python-sdk.git

# Create a new branch for your feature (see "Commit and Branch Conventions" below)
git checkout -b feature/your-feature

# Install dependencies
uv sync

# Install git hooks that enforce commit conventions (one-time, opt-in)
make install-hooks

# Verify your setup works
make test
```

**Note: commit and branch conventions**
Commits follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) and branches follow [Conventional Branches](https://conventionalbranch.org). Run `make install-hooks` once per clone to enable the local git hooks that enforce these.

### 2. Development flow
Here's the recommended workflow for making changes
```
# Make your changes to the code
# ...

# Fix automatically formatting and safe linting issues
make lint-fix

# Run linting and format checks (matches CI exactly)
make lint

# Ensure type checking passes
make type-check

# Run tests to ensure nothing is broken
make test

# Commit your changes (must follow Conventional Commits, see above)
git add .
git commit -m "feat(scope): your descriptive commit message"

# Push and create a PR (branch must follow Conventional Branches, see above)
git push origin feature/your-feature
```

### 3. Testing the in-dev SDK

Inside the clone, `uv sync` already installs `lighton` in editable mode, so your changes are live with no extra step:

```bash
uv run python -c "import lighton; print(lighton.__file__)"  # -> your clone, not site-packages
```

To use your in-dev version **from another project**, add it as an editable path dependency. Edits in the clone take effect immediately, no reinstall:

```bash
cd /path/to/your-project
uv add --editable /path/to/lighton-python-sdk
```

To pull a branch straight from GitHub instead — for reviewing someone else's PR, or testing on a machine without the clone:

```bash
# a branch (note: uv caches git deps, so --upgrade-package is needed to pick up new commits)
uv add "lighton @ git+https://github.com/lightonai/lighton-python-sdk@main"
uv sync --upgrade-package lighton

# a contributor's fork and branch
uv add "lighton @ git+https://github.com/THEIR_USERNAME/lighton-python-sdk@feature/their-feature"
```

Set `LIGHTON_API_KEY` in the consuming project's environment as usual — see the [README](README.md).

Remove it again with `uv remove lighton` (then `uv add lighton` for the released version).
