# helper/script_runner.py
import os
import subprocess
import logging
import asyncio
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class ScriptRunner:
    """Utility for running external scripts securely"""
    
    def __init__(self, script_paths: Dict[str, str]):
        """Initialize with mapping of script names to file paths"""
        self.allowed_scripts = {}
        
        # Register allowed scripts
        for script_name, script_path in script_paths.items():
            self.register_script(script_name, script_path)
    
    def register_script(self, script_name: str, script_path: str) -> bool:
        """Register a script as allowed to run"""
        if not os.path.isfile(script_path):
            logger.warning(f"Script file not found: {script_path}")
            return False
            
        # Store the absolute path
        self.allowed_scripts[script_name] = os.path.abspath(script_path)
        return True
    
    def execute(self, script_name: str, args: List[str] = None) -> Dict[str, Any]:
        """
        Execute a registered script with provided arguments
        
        Args:
            script_name: Name of the script to run
            args: Command-line arguments to pass to the script
            
        Returns:
            Dictionary with execution results
        """
        # Verify script is authorized
        if script_name not in self.allowed_scripts:
            logger.error(f"Attempted to run unauthorized script: {script_name}")
            return {"success": False, "error": "Unauthorized script"}
            
        script_path = self.allowed_scripts[script_name]
        args = args or []
        
        try:
            # Run the script with arguments
            result = subprocess.run(
                [script_path] + args,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Process output
            return {
                "success": True,
                "output": result.stdout,
                "error": result.stderr,
                "command": script_name,
                "args": args
            }
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "output": e.stdout,
                "error": e.stderr or str(e),
                "command": script_name,
                "args": args,
                "returncode": e.returncode
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "command": script_name,
                "args": args
            }
    
    async def execute_async(self, script_name: str, args: List[str] = None) -> Dict[str, Any]:
        """
        Execute a script asynchronously
        
        This runs the actual execution in a thread pool to avoid
        blocking the event loop.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.execute, script_name, args)