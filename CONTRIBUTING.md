# Contributing

Thanks for helping improve Computer Agent.

## Development setup

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## Quality checks

Before opening a PR, run:

```powershell
ruff check .
pytest
```

## Pull request guidance

- Keep changes focused and easy to review.
- Prefer small, well-tested improvements.
- Include a short summary of the problem and the fix.
- If the change affects user-facing features, update the README when needed.

## Reporting issues

Open an issue with:

- a clear description of the problem,
- reproduction steps,
- the model/provider in use,
- and any relevant screenshots or logs.

This project is primarily aimed at Windows desktop automation, so troubleshooting details are especially helpful.
