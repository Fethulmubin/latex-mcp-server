import os
import uuid
import subprocess
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from starlette.responses import Response


# Load local .env file if present
load_dotenv()

from mcp.server.mcpserver import MCPServer
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import boto3
from botocore.config import Config
import uvicorn

PORT = int(os.environ.get("PORT", 8000))

# Cloudflare R2 Configuration
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "latex-pdf").strip()
R2_PUBLIC_DOMAIN = os.environ.get("R2_PUBLIC_DOMAIN", "").strip().rstrip("/")


# Clean, professional TeX document icon (SVG)
LATEX_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" rx="14" fill="#1E293B"/>
  <path d="M16 14h20l12 12v24a2 2 0 0 1-2 2H16a2 2 0 0 1-2-2V16a2 2 0 0 1 2-2z" fill="#3B82F6"/>
  <path d="M36 14v12h12z" fill="#60A5FA"/>
  <text x="32" y="47" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" 
        font-weight="900" font-size="13" fill="#FFFFFF" text-anchor="middle" letter-spacing="0.5">TeX</text>
</svg>"""


def get_s3_client():
    if not (R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY):
        return None
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4")
    )

def upload_pdf_to_r2(pdf_bytes: bytes, filename: str) -> str:
    """Uploads PDF to Cloudflare R2 and returns direct HTTPS download URL."""
    client = get_s3_client()
    if not client or not R2_PUBLIC_DOMAIN:
        missing = []
        if not R2_ACCOUNT_ID: missing.append("R2_ACCOUNT_ID")
        if not R2_ACCESS_KEY_ID: missing.append("R2_ACCESS_KEY_ID")
        if not R2_SECRET_ACCESS_KEY: missing.append("R2_SECRET_ACCESS_KEY")
        if not R2_PUBLIC_DOMAIN: missing.append("R2_PUBLIC_DOMAIN")
        raise ValueError(f"Missing environment variables: {', '.join(missing)}")

    object_key = f"{uuid.uuid4().hex[:10]}_{filename}.pdf"
    
    client.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=object_key,
        Body=pdf_bytes,
        ContentType="application/pdf",
        ContentDisposition=f'inline; filename="{filename}.pdf"'
    )
    return f"{R2_PUBLIC_DOMAIN}/{object_key}"

# Initialize MCP Server
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
    """
   Compiles complete LaTeX source code into publication-quality PDF documents using Tectonic, 
    uploads the output to Cloudflare R2 CDN, and returns an instant HTTPS download link.

    CAPABILITIES:
    - Typesets technical cheat sheets, formula sheets, academic briefs, resumes/CVs, problem sets, and mathematical summaries.
    - Supports modern typography, multicol layouts, math environments (amsmath/amssymb), booktabs, microtype, and tcolorbox cards.
    - Automatically handles self-correction: if a compilation error is returned, review the compiler output, fix the TeX syntax, and invoke this tool again.

    WHEN TO USE:
    - Invoke automatically whenever the user asks for a document, cheat sheet, formula reference, printable PDF, paper summary, or styled technical sheet.
    - You do not need to wait for explicit mentions of '@LaTeX to PDF' if the user's intent clearly asks for a downloadable, compiled, or formatted PDF document.

    EXAMPLE PROMPTS:
    - "@LaTeX to PDF generate a 1-page formula cheat sheet for Signals and Systems"
    - "Create a clean 2-column reference guide on Convolutional Neural Networks and export to PDF"
    - "Typeset an academic summary of TCP vs UDP protocols with a comparison table"
    - "Design a minimal, modern one-page software engineering resume in PDF"

    OUTPUT BEHAVIOR:
    - The tool returns a CDN download link upon success.
    - Present the result to the user as a clean Markdown link: [Download <Document Name>.pdf](DOWNLOAD_URL).
    - Do not dump the raw LaTeX code into the chat unless explicitly requested by the user.

    Args:
        latex_source: The complete, self-contained LaTeX document string starting with \\documentclass and ending with \\end{document}.
        filename: A short, descriptive snake_case name for the generated document (without file extension).
    """
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

            # Upload to Cloudflare R2
            try:
                download_url = upload_pdf_to_r2(pdf_bytes, filename)
            except Exception as upload_err:
                return f"STORAGE_ERROR: Failed to upload PDF to R2: {str(upload_err)}"

            return (
                f"SUCCESS: PDF compiled successfully ({len(pdf_bytes)} bytes).\n"
                f"DOWNLOAD_URL: {download_url}\n"
                f"INSTRUCTION FOR AI: Present this link as a clean, clickable Markdown link: "
                f"[Download {filename}.pdf]({download_url}) in your response."
            )

        except subprocess.TimeoutExpired:
            return "COMPILATION_ERROR: Compilation timed out after 60 seconds."
        except Exception as e:
            return f"SYSTEM_ERROR: {str(e)}"

# Extract base MCP application
mcp_app = mcp.streamable_http_app() if hasattr(mcp, "streamable_http_app") else mcp.app

class MCPCloudHostMiddleware:
    def __init__(self, inner_app):
        self.inner_app = inner_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")

            # 1. Serve favicon and app icon requests
            if path in ["/favicon.ico", "/icon.png", "/apple-touch-icon.png", "/icon.svg"]:
                response = Response(
                    content=LATEX_ICON_SVG,
                    media_type="image/svg+xml",
                    headers={
                        "Cache-Control": "public, max-age=86400",
                        "Content-Type": "image/svg+xml"
                    }
                )
                await response(scope, receive, send)
                return

            # 2. OAuth discovery probes
            if path.startswith("/.well-known/oauth-protected-resource"):
                response = JSONResponse({}, status_code=200)
                await response(scope, receive, send)
                return

            # 3. Normalize path
            if path in ["/mcp", "/mcp/"]:
                scope["path"] = "/mcp"

            # 4. Rewrite Host header to satisfy MCP SDK validation
            new_headers = []
            for name, value in scope.get("headers", []):
                if name.lower() == b"host":
                    new_headers.append((b"host", b"localhost:8000"))
                else:
                    new_headers.append((name, value))
            scope["headers"] = new_headers

        await self.inner_app(scope, receive, send)

app = CORSMiddleware(
    MCPCloudHostMiddleware(mcp_app),
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

if __name__ == "__main__":
    client_status = "Configured" if get_s3_client() else "NOT Configured"
    print(f"--> R2 Storage Client Status: {client_status}")
    print(f"--> R2 Public Domain: {R2_PUBLIC_DOMAIN or 'MISSING'}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")