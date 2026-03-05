"""Distributed Worker — continuously processes tasks from the brain queue.

Each device runs a worker that claims and executes tasks based on capabilities.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import subprocess
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from brain.client import BrainClient

logger = logging.getLogger(__name__)


class DistributedWorker:
    """Continuous task processor for the distributed brain.
    
    Runs on every device, claims tasks matching its capabilities,
    executes them immediately, stores results.
    """
    
    def __init__(self, brain_client: Optional[BrainClient] = None):
        self.brain = brain_client or BrainClient()
        self.node_id = f"{socket.gethostname()}-{os.getpid()}"
        self.capabilities = self._detect_capabilities()
        self.running = False
        self._handlers: Dict[str, Callable] = {}
        self._register_default_handlers()
        
    def _detect_capabilities(self) -> List[str]:
        """Detect what this node can do."""
        caps = ["general", "shell", "file_ops", "git"]
        
        # Check for GPU
        if self._has_gpu():
            caps.append("gpu")
            caps.append("creative")
            caps.append("image_gen")
            caps.append("video_gen")
        
        # Check for internet
        if self._has_internet():
            caps.append("web")
            caps.append("research")
        
        # Check memory
        mem_gb = self._get_memory_gb()
        if mem_gb > 16:
            caps.append("large_model")
        if mem_gb > 32:
            caps.append("huge_model")
        
        # Check for specific tools
        if self._has_command("ollama"):
            caps.append("ollama")
        if self._has_command("docker"):
            caps.append("docker")
        if self._has_command("cargo"):
            caps.append("rust")
        
        logger.info(f"Worker capabilities: {caps}")
        return caps
    
    def _has_gpu(self) -> bool:
        """Check for NVIDIA or AMD GPU."""
        try:
            # Check for nvidia-smi
            result = subprocess.run(
                ["nvidia-smi"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            pass

        # Check for ROCm
        if os.path.exists("/opt/rocm"):
            return True
        
        # Check for Apple Silicon Metal
        if os.uname().sysname == "Darwin":
            try:
                result = subprocess.run(
                    ["system_profiler", "SPDisplaysDataType"],
                    capture_output=True, text=True, timeout=5
                )
                if "Metal" in result.stdout:
                    return True
            except (OSError, subprocess.SubprocessError):
                pass

        return False

    def _has_internet(self) -> bool:
        """Check if we have internet connectivity."""
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "3", "https://1.1.1.1"],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _get_memory_gb(self) -> float:
        """Get total system memory in GB."""
        try:
            if os.uname().sysname == "Darwin":
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True, text=True
                )
                bytes_mem = int(result.stdout.strip())
                return bytes_mem / (1024**3)
            else:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            kb = int(line.split()[1])
                            return kb / (1024**2)
        except (OSError, ValueError):
            pass
        return 8.0  # Assume 8GB if we can't detect
    
    def _has_command(self, cmd: str) -> bool:
        """Check if command exists."""
        try:
            result = subprocess.run(
                ["which", cmd], capture_output=True, timeout=5
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _register_default_handlers(self):
        """Register built-in task handlers."""
        self._handlers = {
            "shell": self._handle_shell,
            "creative": self._handle_creative,
            "code": self._handle_code,
            "research": self._handle_research,
            "general": self._handle_general,
        }
    
    def register_handler(self, task_type: str, handler: Callable[[str], Any]):
        """Register a custom task handler.
        
        Args:
            task_type: Type of task this handler handles
            handler: Async function that takes task content and returns result
        """
        self._handlers[task_type] = handler
        if task_type not in self.capabilities:
            self.capabilities.append(task_type)
    
    # ──────────────────────────────────────────────────────────────────────────
    # Task Handlers
    # ──────────────────────────────────────────────────────────────────────────
    
    async def _handle_shell(self, command: str) -> str:
        """Execute shell command via ZeroClaw or direct subprocess."""
        # Try ZeroClaw first if available
        if self._has_command("zeroclaw"):
            proc = await asyncio.create_subprocess_shell(
                f"zeroclaw exec --json '{command}'",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            # Store result in brain
            await self.brain.remember(
                content=f"Shell: {command}\nOutput: {stdout.decode()}",
                tags=["shell", "result"],
                source=self.node_id,
                metadata={"command": command, "exit_code": proc.returncode}
            )
            
            if proc.returncode != 0:
                raise Exception(f"Command failed: {stderr.decode()}")
            return stdout.decode()
        
        # Fallback to direct subprocess (less safe)
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            raise Exception(f"Command failed: {stderr.decode()}")
        return stdout.decode()
    
    async def _handle_creative(self, prompt: str) -> str:
        """Generate creative media (requires GPU)."""
        if "gpu" not in self.capabilities:
            raise Exception("GPU not available on this node")
        
        # This would call creative tools (Stable Diffusion, etc.)
        # For now, placeholder
        logger.info(f"Creative task: {prompt[:50]}...")
        
        # Store result
        result = f"Creative output for: {prompt}"
        await self.brain.remember(
            content=result,
            tags=["creative", "generated"],
            source=self.node_id,
            metadata={"prompt": prompt}
        )
        
        return result
    
    async def _handle_code(self, description: str) -> str:
        """Code generation and modification."""
        # Would use LLM to generate code
        # For now, placeholder
        logger.info(f"Code task: {description[:50]}...")
        return f"Code generated for: {description}"
    
    async def _handle_research(self, query: str) -> str:
        """Web research."""
        if "web" not in self.capabilities:
            raise Exception("Internet not available on this node")
        
        # Would use browser automation or search
        logger.info(f"Research task: {query[:50]}...")
        return f"Research results for: {query}"
    
    async def _handle_general(self, prompt: str) -> str:
        """General LLM task via local Ollama."""
        if "ollama" not in self.capabilities:
            raise Exception("Ollama not available on this node")
        
        # Call Ollama
        try:
            proc = await asyncio.create_subprocess_exec(
                "curl", "-s", "http://localhost:11434/api/generate",
                "-d", json.dumps({
                    "model": "llama3.1:8b-instruct",
                    "prompt": prompt,
                    "stream": False
                }),
                stdout=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            
            response = json.loads(stdout.decode())
            result = response.get("response", "No response")
            
            # Store in brain
            await self.brain.remember(
                content=f"Task: {prompt}\nResult: {result}",
                tags=["llm", "result"],
                source=self.node_id,
                metadata={"model": "llama3.1:8b-instruct"}
            )
            
            return result
            
        except Exception as e:
            raise Exception(f"LLM failed: {e}")
    
    # ──────────────────────────────────────────────────────────────────────────
    # Main Loop
    # ──────────────────────────────────────────────────────────────────────────
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a claimed task."""
        task_type = task.get("type", "general")
        content = task.get("content", "")
        task_id = task.get("id")
        
        handler = self._handlers.get(task_type, self._handlers["general"])
        
        try:
            logger.info(f"Executing task {task_id}: {task_type}")
            result = await handler(content)
            
            await self.brain.complete_task(task_id, success=True, result=result)
            logger.info(f"Task {task_id} completed")
            return {"success": True, "result": result}
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Task {task_id} failed: {error_msg}")
            await self.brain.complete_task(task_id, success=False, error=error_msg)
            return {"success": False, "error": error_msg}
    
    async def run_once(self) -> bool:
        """Process one task if available.
        
        Returns:
            True if a task was processed, False if no tasks available
        """
        task = await self.brain.claim_task(self.capabilities, self.node_id)
        
        if task:
            await self.execute_task(task)
            return True
        
        return False
    
    async def run(self):
        """Main loop — continuously process tasks."""
        logger.info(f"Worker {self.node_id} started")
        logger.info(f"Capabilities: {self.capabilities}")
        
        self.running = True
        consecutive_empty = 0
        
        while self.running:
            try:
                had_work = await self.run_once()
                
                if had_work:
                    # Immediately check for more work
                    consecutive_empty = 0
                    await asyncio.sleep(0.1)
                else:
                    # No work available - adaptive sleep
                    consecutive_empty += 1
                    # Sleep 0.5s, but up to 2s if consistently empty
                    sleep_time = min(0.5 + (consecutive_empty * 0.1), 2.0)
                    await asyncio.sleep(sleep_time)
                    
            except Exception as e:
                logger.error(f"Worker error: {e}")
                await asyncio.sleep(1)
    
    def stop(self):
        """Stop the worker loop."""
        self.running = False
        logger.info("Worker stopping...")


async def main():
    """CLI entry point for worker."""
    import sys
    
    # Allow capability overrides from CLI
    if len(sys.argv) > 1:
        caps = sys.argv[1].split(",")
        worker = DistributedWorker()
        worker.capabilities = caps
        logger.info(f"Overriding capabilities: {caps}")
    else:
        worker = DistributedWorker()
    
    try:
        await worker.run()
    except KeyboardInterrupt:
        worker.stop()
        print("\nWorker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
