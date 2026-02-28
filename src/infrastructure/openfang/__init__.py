"""OpenFang — vendored binary sidecar for agent tool execution.

OpenFang is a Rust-compiled Agent OS that provides real tool execution
(browser automation, OSINT, forecasting, social management) in a
WASM-sandboxed runtime.  Timmy's coordinator dispatches to it as a
tool vendor rather than a co-orchestrator.

Usage:
    from infrastructure.openfang import openfang_client

    # Check if OpenFang is available
    if openfang_client.healthy:
        result = await openfang_client.execute_hand("browser", params)
"""

from infrastructure.openfang.client import OpenFangClient, openfang_client

__all__ = ["OpenFangClient", "openfang_client"]
