# LaTeX to PDF MCP Server

<div align="center">

[![M8ven Score](https://m8ven.ai/badge/mcp/fethulmubin-latex-mcp-server-za472i?v=c728982529ee2c210b0cbbe1ce0122e0?variant=verified)](https://m8ven.ai/mcp/fethulmubin-latex-mcp-server-za472i?s=readme)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?logo=docker&logoColor=white)](Dockerfile)
[![Protocol](https://img.shields.io/badge/MCP-Streamable%20HTTP-black)](https://modelcontextprotocol.io)
[![Cloudflare R2](https://img.shields.io/badge/Storage-Cloudflare%20R2-F38020?logo=cloudflare&logoColor=white)](https://www.cloudflare.com/products/r2/)

**A remote Model Context Protocol (MCP) server that compiles LaTeX documents into publication-quality PDFs via Tectonic and serves them via Cloudflare R2 CDN.**

[Features](#-key-features) • [Quick Start](#-quick-start) • [Client Configuration](#-client-configuration) • [Architecture](#-architecture) • [Deployment](#-deployment)

</div>

---

## 🚀 Key Features

- **Blazing-Fast Typesetting**: Powered by a statically-linked [Tectonic](https://tectonic-typesetting.github.io/) engine (`musl`), eliminating bulky TeX Live dependencies and dynamic link issues.
- **Global CDN Delivery**: Direct PDF uploads to **Cloudflare R2** with zero egress fees and automated 24-hour lifecycle expiration.
- **Autonomous Error Self-Correction**: When syntax or rendering errors occur, raw compiler diagnostics are fed back to the LLM agent to automatically correct markup in the loop.
- **Universal Multi-Client Support**: Out-of-the-box support for **Gemini Spark**, **Claude Desktop / Claude Agent**, and **ChatGPT (via REST Actions)**.
- **Streamable HTTP & Host Resilience**: Built with Starlette and FastMCP, featuring ASGI-level header normalization for reverse proxies like Render and Cloudflare.

---

## 🛠️ Tools & Capabilities

### `compile_latex`
Compiles raw LaTeX source code into a publication-quality PDF.

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `latex_source` | `string` | **Yes** | Full LaTeX source code starting with `\documentclass` and ending with `\end{document}`. |
| `filename` | `string` | No | Short snake_case name for the output file (default: `"document"`). |

**Output**: Returns the Cloudflare R2 CDN URL formatted as a clean, direct download link.

---

## 🔌 Client Configuration

### 1. Gemini (Spark / Custom Connected Apps)
1. Navigate to **gemini.google.com/spark/apps** or **Settings → Connected Apps**.
2. Click **Connect custom app**.
3. Enter your remote endpoint:
   ```text
   https://latex-mcp-server.onrender.com/mcp[.onrender.com/mcp](https://.onrender.com/mcp)
