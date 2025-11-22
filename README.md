# Gedit LLaMA Plugin

A Gedit plugin that integrates with openai API compatible local LLM servers (like llama.cpp) to ask questions about selected text.

## Features

- **Context-Aware Prompts**: Automatically includes selected text in your prompt when asking LLaMA questions.
- **Streaming Support**: Displays responses as they arrive, providing real-time output from the model.
- **Customizable Configuration**: Easily configure API URL, API key, model name and keyboard shortcut.
- **Multi-line Prompt Input**: Use a multi-line text area to compose complex prompts.
- **Copy To Clipboard**: button to copy LLM response to clipboard.

## Requirements

- Gedit 44+
- Python 3.x
- `requests` library (install with `pip install requests` or via your distro's package manager `python3-requests`)

## Installation

1. **Install the schema**:
   ```bash
   cp org.gnome.gedit.plugins.gedit_llama.gschema.xml ~/.local/share/glib-2.0/schemas/
   glib-compile-schemas ~/.local/share/glib-2.0/schemas/
   ```

2. **Copy plugin files**:
   ```bash
   mkdir -p ~/.local/share/gedit/plugins
   unzip gedit_LLaMA.zip -d ~/.local/share/gedit/plugins/
   ```

3. **Enable the plugin**:
   - Open Gedit
   - Go to `Edit` → `Preferences` → `Plugins`
   - Enable "Gedit LLaMA"

## Usage

1. **Select text** in your document (optional)
2. **Right-click** in the editor and choose `Gedit LLaMA` → `Ask LLaMA`
3. **Enter a prompt** in the dialog
4. **View results** in a popup dialog that shows real-time streaming output

## Configuration

You can customize:
- API URL (default: `http://127.0.0.1:5000/v1/chat/completions`)
- API Key (if required by your server)
- Model name (default: `llama.cpp`)
- Keyboard shortcut (default: `<Ctrl><Alt>l`)

Access the configuration via:
- Right-click menu → `Configure LLaMA`

## How It Works

1. Select text in your document
2. Right-click and select "Ask LLaMA"
3. Enter your question or instruction
4. Plugin sends selected text (if any) + prompt to your local LLM server
5. Response is displayed in a streaming popup dialog

## Example Use Cases

- Explain selected code snippets
- Generate documentation for code
- Find bugs or suggest improvements
- Summarize selected text
- Translate code comments
- Debugging assistance
- Code generation based on context

## Notes

- Requires a local LLM server like llama.cpp running at the configured URL
- Supports both streaming and non-streaming responses
- Plugin automatically detects when new tabs are opened and connects to their views
- Uses GSettings for persistent configuration storage

## Troubleshooting

If you encounter issues:
1. Ensure your local LLM server is running and accessible at the specified URL
2. Verify that `requests` is installed (`pip install requests`)
3. Check that the schema file was properly compiled using `glib-compile-schemas`
4. Confirm the plugin is enabled in Gedit's preferences

## License

MIT License - see LICENSE file for details.
