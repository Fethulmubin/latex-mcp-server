import os
import subprocess
import tempfile
import base64
from pathlib import Path
# NEW (v2.x)
from mcp.server.mcpserver import MCPServer



# Render injects the PORT environment variable dynamically
PORT = int(os.environ.get("PORT", 8000))

# Initialize FastMCP
mcp = MCPServer("latex-to-pdf", host="0.0.0.0", port=PORT)


# Production-grade baseline typography template fallback
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
    """
    Compiles raw LaTeX markup into a production-grade PDF.
    
    Args:
        latex_source: Complete LaTeX code or document body.
        filename: Base name for the generated document (without .pdf).
        
    Returns:
        A Base64 PDF data-URI upon success, or detailed compiler error logs for self-healing.
    """
    code = latex_source.strip()

    # Auto-wrap if documentclass is omitted
    if r"\documentclass" not in code:
        code = f"{DEFAULT_PREAMBLE}\n\\begin{{document}}\n{code}\n\\end{{document}}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        tex_path = tmp_path / f"{filename}.tex"
        pdf_path = tmp_path / f"{filename}.pdf"

        tex_path.write_text(code, encoding="utf-8")

        # Compile with Tectonic (downloads required CTAN packages on the fly)
        try:
            process = subprocess.run(
                ["tectonic", str(tex_path), "--outdir", str(tmp_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60
            )

            # --- FEEDBACK LOOP FOR COMPILATION ERRORS ---
            if process.returncode != 0:
                raw_log = (process.stderr or process.stdout).strip()
                return (
                    f"COMPILATION_ERROR:\n{raw_log}\n\n"
                    "INSTRUCTION FOR AI: The document failed to build. Examine the error above, "
                    "locate the invalid LaTeX command, missing package, or unescaped character, "
                    "fix the source code, and invoke compile_latex again."
                )

            # Return as Base64 Data URI so web clients can access/download it
            pdf_bytes = pdf_path.read_bytes()
            b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
            
            return (
                f"SUCCESS: PDF created ({len(pdf_bytes)} bytes).\n"
                f"DATA_URI: data:application/pdf;base64,{b64_pdf}"
            )

        except subprocess.TimeoutExpired:
            return "COMPILATION_ERROR: Compilation timed out after 60 seconds. Simplify complex loops or packages."
        except Exception as e:
            return f"SYSTEM_ERROR: {str(e)}"

if __name__ == "__main__":
    # If launched locally via CLI, use stdio; otherwise use SSE for remote hosting
    transport = os.environ.get("MCP_TRANSPORT", "sse")
    mcp.run(transport=transport)