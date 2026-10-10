import os
import subprocess
import tempfile
import base64
from pathlib import Path
from mcp.server.mcpserver import MCPServer
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

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

# 2. Get base MCP application
mcp_app = mcp.streamable_http_app() if hasattr(mcp, "streamable_http_app") else mcp.app

# 3. ASGI Middleware: Normalizes paths, rewrites Host header, and serves OAuth probes
class MCPCloudHostMiddleware:
    def __init__(self, inner_app):
        self.inner_app = inner_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")

            # 1. Answer OAuth probes directly
            if path.startswith("/.well-known/oauth-protected-resource"):
                response = JSONResponse({}, status_code=200)
                await response(scope, receive, send)
                return

            # 2. Normalize path so /mcp and /mcp/ always match the internal route
            if path in ["/mcp", "/mcp/"]:
                scope["path"] = "/mcp"

            # 3. Rewrite the Host header to satisfy internal SDK validation
            new_headers = []
            for name, value in scope.get("headers", []):
                if name.lower() == b"host":
                    new_headers.append((b"host", b"localhost:8000"))
                else:
                    new_headers.append((name, value))
            scope["headers"] = new_headers

        await self.inner_app(scope, receive, send)

# 4. Wrap with CORS
app = CORSMiddleware(
    MCPCloudHostMiddleware(mcp_app),
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")