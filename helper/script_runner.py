import os
import subprocess
import logging
import asyncio
from typing import Dict, List, Any
import hashlib

logger = logging.getLogger(__name__)

class ScriptRunner:
    """Utility for running external scripts securely with hash verification"""
    
    def __init__(self, script_paths: Dict[str, str], script_hashes: Dict[str, str] = None):
        """Initialize with mapping of script names to file paths and expected hashes"""
        self.allowed_scripts = {}
        self.script_hashes = script_hashes or {}
        
        # Register allowed scripts
        for script_name, script_path in script_paths.items():
            self.register_script(script_name, script_path)
    
    def _calculate_script_hash(self, script_path: str) -> str:
        """Calculate SHA-256 hash of a script file"""
        try:
            with open(script_path, 'rb') as f:
                file_content = f.read()
            return hashlib.sha256(file_content).hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate hash for {script_path}: {e}")
            return None
    
    def register_script(self, script_name: str, script_path: str) -> bool:
        """Register a script as allowed to run and store its hash"""
        # Check if script already exists - reject duplicate registrations
        if script_name in self.allowed_scripts:
            logger.warning(f"Script with name '{script_name}' is already registered")
            return False
            
        if not os.path.isfile(script_path):
            logger.warning(f"Script file not found: {script_path}")
            return False
            
        # Store the absolute path
        abs_path = os.path.abspath(script_path)
        self.allowed_scripts[script_name] = abs_path
        
        # Calculate and store hash if not provided
        if script_name not in self.script_hashes:
            script_hash = self._calculate_script_hash(abs_path)
            if script_hash:
                self.script_hashes[script_name] = script_hash
                logger.info(f"Registered script {script_name} with hash {script_hash}")
            else:
                logger.warning(f"Could not calculate hash for {script_name}")
        
        return True
    
    def verify_script_integrity(self, script_name: str) -> bool:
        """Verify the integrity of a script by comparing its hash to the stored hash"""
        if script_name not in self.allowed_scripts:
            return False
        
        if script_name not in self.script_hashes:
            logger.warning(f"No hash available for script verification: {script_name}")
            return True  # Consider if you want to fail open or closed here
        
        script_path = self.allowed_scripts[script_name]
        current_hash = self._calculate_script_hash(script_path)
        expected_hash = self.script_hashes[script_name]
        
        if current_hash != expected_hash:
            logger.error(f"Script integrity check failed for {script_name}")
            logger.error(f"Expected hash: {expected_hash}")
            logger.error(f"Actual hash: {current_hash}")
            return False
        
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
        
        # Verify script integrity
        if not self.verify_script_integrity(script_name):
            return {"success": False, "error": "Script integrity check failed"}
            
        script_path = self.allowed_scripts[script_name]
        if args and len(args) > 0:
            logger.warning(f"Arguments were provided but will be ignored for script {script_name}: {args}")
        
        try:
            # Run the script with arguments
            result = subprocess.run(
                [script_path],
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
                "args": []
            }
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "output": e.stdout,
                "error": e.stderr or str(e),
                "command": script_name,
                "args": [],
                "returncode": e.returncode
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "command": script_name,
                "args": []
            }
    
    async def execute_async(self, script_name: str, args: List[str] = None) -> Dict[str, Any]:
        """
        Execute a script asynchronously with integrity verification

        This runs the actual execution in a thread pool to avoid
        blocking the event loop.
        """
        # Verify script is authorized
        if script_name not in self.allowed_scripts:
            logger.error(f"Attempted to run unauthorized script asynchronously: {script_name}")
            return {"success": False, "error": "Unauthorized script"}

        # Verify script integrity - do this synchronously since it's quick
        if not self.verify_script_integrity(script_name):
            return {"success": False, "error": "Script integrity check failed"}

        # Run the actual execution in a thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.execute, script_name, args)