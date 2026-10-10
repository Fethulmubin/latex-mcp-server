import os
import subprocess
import tempfile
import base64
from pathlib import Path
from mcp.server.mcpserver import MCPServer
from starlette.middleware.cors import CORSMiddleware

PORT = int(os.environ.get("PORT", 8000))

# 1. Initialize MCP Server
mcp = MCPServer("latex-to-pdf")

DEFAULT_PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=1in]{geometry}
\usepackage{microtype}
\usepackage{booktabs}
\usepackage{amsmath,amssymb}
\usepackage{xcolor}
\usepackage{hyperref}
\hypersetup{colorlinks=true, linkcolor=blue!70!black, urlcolor=blue!70!black}
"""

@mcp.tool()
def compile_latex(latex_source: str, filename: str = "document") -> str:
    """Compiles LaTeX markup into a PDF and returns a Base64 data URI."""
    code = latex_source.strip()
    if r"\documentclass" not in code:
        code = f"{DEFAULT_PREAMBLE}\n\\begin{{document}}\n{code}\n\\end{{document}}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        tex_path = tmp_path / f"{filename}.tex"
        pdf_path = tmp_path / f"{filename}.pdf"

        tex_path.write_text(code, encoding="utf-8")

        try:
            process = subprocess.run(
                ["tectonic", str(tex_path), "--outdir", str(tmp_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60
            )

            if process.returncode != 0:
                raw_log = (process.stderr or process.stdout).strip()
                return (
                    f"COMPILATION_ERROR:\n{raw_log}\n\n"
                    "INSTRUCTION FOR AI: Examine the compiler error above, fix the LaTeX code, "
                    "and invoke compile_latex again."
                )

            pdf_bytes = pdf_path.read_bytes()
            b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
            return (
                f"SUCCESS: PDF created ({len(pdf_bytes)} bytes).\n"
                f"DATA_URI: data:application/pdf;base64,{b64_pdf}"
            )

        except subprocess.TimeoutExpired:
            return "COMPILATION_ERROR: Compilation timed out after 60 seconds."
        except Exception as e:
            return f"SYSTEM_ERROR: {str(e)}"

if __name__ == "__main__":
    # 2. Extract underlying Starlette app and inject CORS middleware
    # This allows gemini.google.com to negotiate preflight requests
    app = mcp.streamable_http_app() if hasattr(mcp, "streamable_http_app") else mcp.app
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id", "content-type"],
    )

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)