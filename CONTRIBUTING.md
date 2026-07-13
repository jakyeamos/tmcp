# Contributing

TMCP is intentionally small and dependency-light. Keep changes portable across macOS, Linux, and Windows.

## Development

Run these checks before opening a PR:

```bash
node --check scripts/tmcp_launcher.mjs
python3 scripts/release_package_compile.py .
python3 -m unittest discover -s tests
python3 scripts/check_contracts.py .
python3 scripts/check_install.py .
python3 scripts/check_release_package.py . --verify-reproducible
pre-cr run --json --workspace .
```

For Claude Code packaging, also run:

```bash
claude plugin validate .
```

## Design Constraints

- Keep standalone mode independent of AIOS.
- Keep AIOS as an optional adapter only.
- Do not add package-manager dependencies unless the release rubric is updated with the added install cost.
- Redact sensitive values before returning harvested excerpts or artifacts.
- Treat check_release_package.py as a clean-Git release build: it intentionally
  rejects dirty tracked trees and unsafe committed release inputs.
- Keep Codex and Claude plugin metadata independently valid.
