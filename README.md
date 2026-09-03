# Computer Agent

Computer Agent is an easy-to-install Windows assistant that can see your screen and help operate your computer. Use private local AI models through Ollama or connect an optional cloud provider such as OpenAI, Anthropic, or OpenRouter. You stay in control: Computer Agent shows what it wants to do and asks before taking consequential actions.

## Current features

- Local models through Ollama (default: `http://localhost:11434/v1`)
- Built-in Ollama model browser/downloader with progress
- Built-in Ollama runtime installer with Windows signature verification
- OpenAI, OpenRouter, LM Studio, or another OpenAI-compatible endpoint
- Anthropic Messages API
- Screenshot context and screen-size awareness
- Mouse click, text entry, hotkeys, PowerShell, file reading, and directory listing
- Approval prompts for computer control, shell commands, and file changes
- Kill switch: move the mouse to the upper-left corner (PyAutoGUI fail-safe)
- Tool-call audit trail in the chat

## Get started

1. Download **ComputerAgent-Setup.exe** from [Releases](https://github.com/benjaminbencsik/Computer-Agent/releases).
2. Open the downloaded file and follow the installer.
3. Start **Computer Agent** from your desktop or Start Menu.
4. Open **Local models**, select **Install Ollama**, and then download the recommended model.

That is all that is required to run Computer Agent privately on your PC. If you already use a paid AI provider, you can connect it later from **Settings**.

## Local models

The **Local models** screen can install Ollama, show models already on your PC, and download new models with progress. Computer Agent verifies the Ollama installer's Windows signature before opening it.

Because Computer Agent works from screenshots, vision-capable models work best. Start with `qwen2.5vl:7b`; the model recommender will eventually select the best option automatically based on your PC's hardware.

## Developer installation

Developers who want to run the source code can install Python 3.11 or newer and use:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
computer-agent
```

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
