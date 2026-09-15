# Computer Agent

Computer Agent is an easy-to-install Windows assistant that can see your screen and help operate your computer. Use private local AI models through Ollama or connect an optional cloud provider such as OpenAI, Anthropic, or OpenRouter. You stay in control: Computer Agent shows what it wants to do and asks before taking consequential actions.

## Current features

- Local models through Ollama (default: `http://localhost:11434/v1`)
- Built-in Ollama model browser/downloader with progress
- Built-in Ollama runtime installer with Windows signature verification
- In-app update checks with SHA-256 verified downloads, checked automatically on
  startup and selectable between stable and beta release channels
- OpenAI, OpenRouter, LM Studio, or another OpenAI-compatible endpoint
- Anthropic Messages API
- Screenshot context and screen-size awareness
- Mouse click, text entry, hotkeys, PowerShell, file reading, and directory listing
- Windows UI Automation tree reading and element clicks grounded in control names/ids
- Browser control grounded in the DOM (Chromium via Playwright): open, snapshot
  interactive elements, click, and type by element index instead of coordinates
- Task checkpoints per conversation, with resume-from-checkpoint and undo for
  the most recent file write
- Zoomed screenshots for precise clicking on small targets, so accuracy holds up on
  the smaller local models a CPU-only or low-VRAM machine needs to run
- Hardware auto-detection ("Recommend for my PC") picks a model sized to fit your
  GPU's VRAM, or your system RAM on machines with no dedicated GPU at all
- Approval prompts for computer control, shell commands, and file changes
- Kill switch: move the mouse to the upper-left corner (PyAutoGUI fail-safe)
- Tool-call audit trail in the chat
- Persistent chat history with a familiar AI-chat sidebar

## Get started

1. Download **ComputerAgent-Setup.exe** from [Releases](https://github.com/benjaminbencsik/Computer-Agent/releases).
2. Open the downloaded file and follow the installer.
3. Start **Computer Agent** from your desktop or Start Menu.
4. Open **Local models**, select **Install Ollama**, and then download the recommended model.

That is all that is required to run Computer Agent privately on your PC. If you already use a paid AI provider, you can connect it later from **Settings**.

## Local models

The **Local models** screen can install Ollama, show models already on your PC, and download new models with progress. Computer Agent verifies the Ollama installer's Windows signature before opening it.

Because Computer Agent works from screenshots, vision-capable models work best. Start with `qwen2.5vl:7b`, or click **Recommend for my PC** to auto-detect your GPU (via `nvidia-smi` or Windows WMI) or system RAM if there's no dedicated GPU, and get a model sized to fit.

## Developer installation

Developers who want to run the source code can install Python 3.11 or newer and use:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
computer-agent
```

Other local runtimes work through the **OpenAI Compatible** provider. Examples include LM Studio, llama.cpp server, Jan, LocalAI, and vLLM. Point the Base URL at that runtime's OpenAI-compatible `/v1` endpoint. Their model downloading remains managed by the runtime itself in this first release.

For a cloud provider, open Settings and enter the endpoint, model, and API key. Each provider's key is stored separately in the OS credential vault (Windows Credential Manager, Keychain, or Secret Service) via `keyring`, never written to the plaintext configuration file.

## Agent protocol

The model receives a screenshot plus a small set of tools. It returns exactly one JSON object at a time:

```json
{"thought":"Need to open Start.","action":{"name":"hotkey","arguments":{"keys":["win"]}}}
```

When finished it returns:

```json
{"thought":"Task is complete.","final":"Done."}
```

When the connected provider/model supports native function calling (OpenAI, Anthropic, and
tool-calling-capable Ollama models), Computer Agent offers the same tools as native tool
calls instead, and falls back to the JSON protocol above automatically if the provider
rejects them. Toggle this in Settings under "Tool calling".

## Safety model

All actions are deny-by-default. Read-only screen inspection can run automatically; input, PowerShell, and filesystem mutations require confirmation unless you explicitly enable session auto-approval. Dangerous PowerShell patterns are blocked even with auto-approval. The app does not attempt to bypass Windows UAC.

## Browser control

Install the optional `browser` extra and Chromium once:

```powershell
pip install -e .[browser]
playwright install chromium
```

The agent can then use `browser_open`, `browser_snapshot`, `browser_click`, and
`browser_type` to drive a real Chromium window grounded in the page's DOM rather than
screen coordinates. Without the extra installed, these actions report a clear error
instead of failing silently.

## MSIX packaging

`packaging/msix/AppxManifest.xml` and `packaging/build_msix.ps1` scaffold an MSIX
alongside the existing Inno Setup installer. Signing requires a real code-signing
certificate that isn't (and shouldn't be) checked into this repository -- see the
comments at the top of `build_msix.ps1` for how to supply your own certificate and
update the manifest's `Publisher` to match its subject. This is not wired into CI
until a certificate is available.

## Roadmap

- [x] Windows UI Automation accessibility tree (more reliable than coordinates)
- [x] Native tool-calling for OpenAI, Anthropic, and Ollama
- [x] Encrypted Windows Credential Manager storage
- [x] Task checkpoints, replay, and undo where possible
- [x] Browser-specific control and DOM grounding
- [x] Auto-update channel (stable/beta), checked automatically on startup
- [ ] Signed MSIX installer (scaffolded; needs a code-signing certificate to sign and ship)

## Development

```powershell
pip install -e .[dev]
ruff check .
pytest
```

## License

MIT
