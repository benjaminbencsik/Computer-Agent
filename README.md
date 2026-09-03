# Computer Agent

A Windows-first desktop agent that can use local Ollama models or paid OpenAI-compatible APIs to see and operate your computer. Every consequential action passes through a local policy layer and can require your approval.

> Early MVP. Run it in a test Windows account or VM until you are comfortable with its behavior.

## Current features

- Local models through Ollama (default: `http://localhost:11434/v1`)
- Built-in Ollama model browser/downloader with progress
- OpenAI, OpenRouter, LM Studio, or another OpenAI-compatible endpoint
- Anthropic Messages API
- Screenshot context and screen-size awareness
- Mouse click, text entry, hotkeys, PowerShell, file reading, and directory listing
- Approval prompts for computer control, shell commands, and file changes
- Kill switch: move the mouse to the upper-left corner (PyAutoGUI fail-safe)
- Tool-call audit trail in the chat

## Quick start on Windows

1. Install Python 3.11 or newer.
2. Clone this repository and open PowerShell in it.
3. Create the environment and install the app:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
computer-agent
```

For local inference, install Ollama, run `ollama pull qwen3:8b`, then choose Ollama in Settings. Models that reliably follow JSON instructions work best.

You can also click **Local models** in the app to view installed Ollama models and download a recommended model. Because the agent sees screenshots, a vision model such as `qwen2.5vl:7b`, `gemma3:12b`, or `llama3.2-vision:11b` is the best fit when your hardware can run it.

Other local runtimes work through the **OpenAI Compatible** provider. Examples include LM Studio, llama.cpp server, Jan, LocalAI, and vLLM. Point the Base URL at that runtime's OpenAI-compatible `/v1` endpoint. Their model downloading remains managed by the runtime itself in this first release.

For a cloud provider, open Settings and enter the endpoint, model, and API key. Secrets are held only for the current session in this MVP; they are not written to the configuration file.

## Agent protocol

The model receives a screenshot plus a small set of tools. It returns exactly one JSON object at a time:

```json
{"thought":"Need to open Start.","action":{"name":"hotkey","arguments":{"keys":["win"]}}}
```

When finished it returns:

```json
{"thought":"Task is complete.","final":"Done."}
```

This deliberately keeps execution provider-neutral. A future release can add native tool-calling adapters per provider.

## Safety model

All actions are deny-by-default. Read-only screen inspection can run automatically; input, PowerShell, and filesystem mutations require confirmation unless you explicitly enable session auto-approval. Dangerous PowerShell patterns are blocked even with auto-approval. The app does not attempt to bypass Windows UAC.

## Roadmap

- Windows UI Automation accessibility tree (more reliable than coordinates)
- Native tool-calling for OpenAI, Anthropic, and Ollama
- Encrypted Windows Credential Manager storage
- Task checkpoints, replay, and undo where possible
- Browser-specific control and DOM grounding
- Signed MSIX installer and auto-update channel

## Development

```powershell
pip install -e .[dev]
ruff check .
pytest
```

## License

MIT
