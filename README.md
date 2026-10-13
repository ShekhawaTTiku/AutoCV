# 📄 AutoCV

> **An AI-powered LaTeX resume editor with targeted section editing, live compilation, and human-in-the-loop review.**

---

## 🚀 Quickstart: How to Run the Project

Follow these steps to set up and run AutoCV on your machine.

### 1. Prerequisites
- **Python 3.9+** installed and available on your system.
- API keys from:
  - [Google AI Studio](https://aistudio.google.com/) (`GEMINI_API_KEY`)
  - [Groq Console](https://console.groq.com/) (`GROQ_API_KEY`)
  - [Mistral AI Console](https://console.mistral.ai/) (`MISTRAL_API_KEY`)

---

### 2. Automatic Setup

Open your terminal or PowerShell in the project directory:

**Windows:**
```powershell
python setup.py
```
*(Or simply double-click `setup.bat`)*

**macOS / Linux:**
```bash
python3 setup.py
```
*(Or run `./setup.sh`)*

#### What the setup script does automatically:
1. Installs all required Python dependencies (`streamlit`, `pymupdf`, `httpx`).
2. Creates your `.env` configuration file from `.env.example`.
3. Checks for a LaTeX compiler (`tectonic`, `pdflatex`, `xelatex`). If none is found on your system, it automatically downloads and extracts the standalone, portable **Tectonic** binary into `tools/`.

---

### 3. Add Your API Keys

Open the newly created `.env` file in any text editor and fill in your keys:

```ini
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
MISTRAL_API_KEY=your_mistral_api_key_here
```

*(Optional model overrides, token limits, and timeouts can also be customized in `.env`)*

---

### 4. Launch the Application

Run the Streamlit app:

```bash
streamlit run app.py
```

Open your browser at **`http://localhost:8501`**.

---

## 💡 About AutoCV

### The Problem
Traditional LLMs often struggle when editing LaTeX resumes:
- They rewrite the entire file, changing established styling, macros, and spacing.
- They introduce subtle syntax errors (`\begin{itemize}` without `\end{itemize}`, unescaped `%` or `&`, broken braces).
- They produce unvetted changes without human oversight.

### The AutoCV Solution
AutoCV introduces a **multi-agent, human-in-the-loop pipeline** designed specifically for LaTeX documents:

```
[User Request] 
      │
      ▼
1. Section Router (Gemini) ──► Identifies only the targeted section (e.g., Experience)
      │
      ▼
2. Precision Editor (Groq) ──► Modifies only the selected snippet; leaves the rest intact
      │
      ▼
3. Local Engine ─────────────► Applies exact patch & compiles PDF candidate
      │
      ├── (Compilation Error?) ──► Auto-Repair (Groq ➔ Mistral fallback)
      ▼
4. Multi-Page Preview ───────► Human reviews diff & compiled PDF with jump pills
      │
      ├── [Approve] ─────────► Promoted to Approved Baseline (Download PDF / TeX)
      └── [Reject]  ─────────► Candidate discarded; baseline restored
```

---

## ✨ Key Features

- **🎯 Targeted Section-Level Editing**: Instead of rewriting entire templates, Gemini analyzes the document structure and identifies the exact section to edit. Only that section is sent to Groq for modifications.
- **🛡️ Human-in-the-Loop Approval**: Edits are compiled into temporary **candidates**. You can review the compiled PDF and diff before deciding to approve or reject. Unapproved changes never overwrite your approved baseline.
- **📜 Smooth Scrollable Multi-Page Preview**: Multi-page resumes render inside a responsive scrollable container equipped with quick-jump pill buttons (`[1] [2] [3] [4]`) to jump directly to any page.
- **🔧 Automatic Compilation Repair (Multi-Provider Fallback)**:
  - If a generated candidate fails LaTeX compilation, Groq is automatically prompted to produce exact surgical patches.
  - If Groq's repair fails, the pipeline immediately falls back to **Mistral Large** with compiler logs and error context.
  - A manual **"Try fix with Mistral"** button is also available for compilation errors in uploaded files.
- **⚡ Portable LaTeX Compilation**: Uses [Tectonic](https://tectonic-typesetting.github.io/), a modern, self-contained TeX engine that downloads needed packages on the fly with no multi-gigabyte TeX distributions required.
- **🔒 Session & Budget Guardrails**: Built-in request limits, token budgets, compilation timeouts, and isolated temporary workspaces to keep editing fast, reliable, and secure.

---

## 📁 Project Structure

```text
AutoCV/
├── src/                        # Modular single-responsibility core package
│   ├── config.py               # Settings dataclass & environment reader
│   ├── constants.py            # Global limits, command sets, and LaTeX commands
│   ├── exceptions.py           # Domain exception hierarchy & cancellation checks
│   ├── models.py               # Project, Section, Usage, Outcome, EditResult
│   ├── pdf.py                  # Thread-safe PyMuPDF page rasterization
│   ├── project_io.py           # Safe project ingestion, ZIP export, fingerprints
│   ├── latex_parser.py         # LaTeX AST & regex parser, section extraction & replacement
│   ├── patcher.py              # Surgical patch validator & application engine
│   ├── compiler.py             # Sandbox isolation, preflight checks, Tectonic runner
│   ├── orchestrator.py         # High-level editing, compilation & repair pipeline
│   ├── ai/                     # Multi-agent AI provider layer
│   │   ├── client.py           # Multi-agent client (Gemini, Groq, Mistral)
│   │   ├── context.py          # Context building & token-bounded asset inventory
│   │   ├── prompts.py          # Strict system instructions & facts preservation policies
│   │   └── schemas.py          # JSON schemas & recursive structure validation
│   └── ui/                     # Streamlit presentation & session state
│       ├── state.py            # Session state, background Job thread, and lifecycle
│       └── components.py       # UI widgets, scrollable multi-page preview, export buttons
├── app.py                      # Main Streamlit application entrypoint
├── core.py                     # Clean facade re-exporting core engine symbols
├── ai.py                       # Clean facade re-exporting AI clients & schemas
├── test_workflow.py            # Complete test suite (routing, patching, repairs)
├── setup.py                    # Automated cross-platform setup script
├── setup.bat                   # 1-click Windows setup launcher
├── setup.sh                    # 1-click Unix/macOS setup launcher
├── requirements.txt            # Python dependencies
├── packages.txt                # System packages for Streamlit Community Cloud
├── .env.example                # Configuration template
├── .gitignore                  # Excludes private keys and compiled binaries
└── tools/                      # Portable Tectonic LaTeX compiler
```

---

## 🧪 Running Tests

To run the full unit and workflow test suite:

```bash
python -B test_workflow.py
```
