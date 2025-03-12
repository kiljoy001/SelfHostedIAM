import subprocess
import logging
from pathlib import Path
from typing import List, Dict

class ScriptRunner:
    def __init__(self, allowed_scripts: Dict[str, Path]):
        self.allowed_scripts = allowed_scripts
        self.logger = logging.getLogger(self.__class__.__name__)

    def _sanitize_args(self, args: List[str]) -> List[str]:
        """Allow only alphanumeric and safe characters"""
        return [a for a in args if all(c.isalnum() or c in '-_./' for c in a)]

    def execute(self, script_name: str, args: List[str] = None) -> dict:
        if script_name not in self.allowed_scripts:
            self.logger.error("Attempted to run unauthorized script: %s", script_name)
            return {"success": False, "error": "Unauthorized script"}

        script_path = self.allowed_scripts[script_name]
        if not script_path.exists():
            return {"success": False, "error": "Script not found"}

        safe_args = self._sanitize_args(args or [])
        
        try:
            result = subprocess.run(
                [str(script_path)] + safe_args,
                check=True,
                capture_output=True,
                text=True,
                timeout=30  # Prevent hanging scripts
            )
            return {
                "success": True,
                "output": result.stdout,
                "artifacts": self._find_artifacts(script_name)
            }
        except subprocess.CalledProcessError as e:
            self.logger.error("Script failed: %s", e.stderr)
            return {"success": False, "error": e.stderr}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Script timed out"}

    def _find_artifacts(self, script_name: str) -> dict:
        """Define expected output files per script"""
        artifacts = {
            "tpm_provision": ["signing_key.pem", "handle.txt"],
            "generate_cert": ["certs/cert.pem", "certs/tpm.key"],
            "random_number": ["tpm_random.bin"]
        }
        return {name: Path(name).exists() for name in artifacts.get(script_name, [])}