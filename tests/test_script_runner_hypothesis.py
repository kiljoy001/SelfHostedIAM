import pytest
import os
import tempfile
import shutil
import string
import hashlib
import asyncio
from typing import Dict, List, Tuple
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant

from helper.script_runner import ScriptRunner

# Define strategies for different test inputs
@st.composite
def script_names(draw):
    """Generate valid script names"""
    return draw(st.text(
        alphabet=string.ascii_letters + string.digits + "_-.",
        min_size=1,
        max_size=30
    ))

@st.composite
def script_contents(draw):
    """Generate valid script contents"""
    # Create a script with a shebang line and some commands
    shebang = draw(st.sampled_from(["#!/bin/sh", "#!/bin/bash", "#!/usr/bin/env python"]))
    
    # Generate 1-10 lines of simple commands
    lines = draw(st.lists(
        st.text(
            alphabet=string.ascii_letters + string.digits + " =-_+.'\"${}()[]",
            min_size=0,
            max_size=50
        ),
        min_size=1,
        max_size=10
    ))
    
    # Add exit code at the end for shell scripts
    if "sh" in shebang:
        exit_code = draw(st.integers(min_value=0, max_value=255))
        lines.append(f"exit {exit_code}")
    
    return f"{shebang}\n" + "\n".join(lines)

@st.composite
def script_arguments(draw):
    """Generate command-line arguments"""
    return draw(st.lists(
        st.text(
            alphabet=string.ascii_letters + string.digits + "_-.",
            min_size=0,
            max_size=30
        ),
        min_size=0,
        max_size=5
    ))

@st.composite
def script_files(draw):
    """Generate a tuple of (script_name, script_path, script_content, script_hash)"""
    name = draw(script_names())
    content = draw(script_contents())
    
    # Create a temporary file with the content
    _, path = tempfile.mkstemp(suffix=".sh")
    with open(path, 'w') as f:
        f.write(content)
    
    # Make the script executable
    os.chmod(path, 0o755)
    
    # Calculate the hash
    script_hash = hashlib.sha256(content.encode()).hexdigest()
    
    return (name, path, content, script_hash)

# Test script registration - use unique names to avoid duplicates
@given(scripts=st.lists(script_files(), min_size=1, max_size=5, unique_by=lambda s: s[0]))
@settings(max_examples=25)  # Limit the number of examples to avoid creating too many files
def test_script_registration(scripts):
    """Test script registration with various inputs"""
    try:
        # Convert list of tuples to two dictionaries
        script_paths = {name: path for name, path, _, _ in scripts}
        script_hashes = {name: hash_val for name, _, _, hash_val in scripts}
        
        # Initialize ScriptRunner with the scripts
        runner = ScriptRunner(script_paths, script_hashes)
        
        # Verify all scripts were registered
        for name, path, _, hash_val in scripts:
            assert name in runner.allowed_scripts, f"Script {name} should be registered"
            assert runner.allowed_scripts[name] == os.path.abspath(path), f"Script path for {name} doesn't match"
            assert runner.script_hashes[name] == hash_val, f"Script hash for {name} doesn't match"
    finally:
        # Clean up temporary files
        for _, path, _, _ in scripts:
            if os.path.exists(path):
                os.unlink(path)

# Modified test for duplicate script rejection - use a single name for both scripts
@given(
    script_name=script_names(),
    content1=script_contents(),
    content2=script_contents()
)
@settings(
    max_examples=25,
    suppress_health_check=[HealthCheck.filter_too_much]  # Suppress health check if needed
)
def test_duplicate_script_rejection(script_name, content1, content2):
    """Test that the script runner rejects scripts with duplicate names"""
    # Create two temporary files with different content
    _, path1 = tempfile.mkstemp(suffix=".sh")
    _, path2 = tempfile.mkstemp(suffix=".sh")
    
    try:
        # Write content to both files
        with open(path1, 'w') as f:
            f.write(content1)
        with open(path2, 'w') as f:
            f.write(content2)
        
        # Make both files executable
        os.chmod(path1, 0o755)
        os.chmod(path2, 0o755)
        
        # Calculate hashes
        hash1 = hashlib.sha256(content1.encode()).hexdigest()
        hash2 = hashlib.sha256(content2.encode()).hexdigest()
        
        # Initialize ScriptRunner with the first script
        runner = ScriptRunner({script_name: path1}, {script_name: hash1})
        
        # Verify first script was registered
        assert script_name in runner.allowed_scripts, f"Script {script_name} should be registered"
        assert runner.allowed_scripts[script_name] == os.path.abspath(path1), f"Script path doesn't match"
        
        # Try to register a script with the same name but different path
        result = runner.register_script(script_name, path2)
        
        # Verify registration failed
        assert result is False, f"Duplicate script {script_name} registration should fail"
        
        # Verify the original script path is still there
        assert runner.allowed_scripts[script_name] == os.path.abspath(path1), \
            f"Original script path should not be overwritten"
    finally:
        # Clean up temporary files
        if os.path.exists(path1):
            os.unlink(path1)
        if os.path.exists(path2):
            os.unlink(path2)

# Test script integrity verification
@given(
    script=script_files(),
    tampered_content=script_contents()
)
@settings(max_examples=25)
def test_script_integrity(script, tampered_content):
    """Test script integrity verification with original and tampered content"""
    name, path, content, hash_val = script
    
    try:
        # Initialize ScriptRunner with the script
        runner = ScriptRunner({name: path}, {name: hash_val})
        
        # Verify script integrity should pass
        assert runner.verify_script_integrity(name), f"Script {name} should pass integrity check"
        
        # Skip if tampered content happens to match the original
        if tampered_content == content:
            assume(False)
        
        # Tamper with the script
        with open(path, 'w') as f:
            f.write(tampered_content)
        
        # Verify script integrity should fail
        assert not runner.verify_script_integrity(name), f"Tampered script {name} should fail integrity check"
    finally:
        # Clean up temporary file
        if os.path.exists(path):
            os.unlink(path)

# Test script execution with mocked subprocess
@given(
    script=script_files(),
    args=script_arguments()
)
@settings(max_examples=25)
def test_script_execution(script, args):
    """Test script execution with various inputs and mocked subprocess"""
    name, path, _, hash_val = script
    
    try:
        # Initialize ScriptRunner with the script
        runner = ScriptRunner({name: path}, {name: hash_val})
        
        # Mock subprocess.run to avoid actually running the script
        with patch('subprocess.run') as mock_run:
            # Configure the mock
            mock_process = MagicMock()
            mock_process.stdout = "Mock output"
            mock_process.stderr = ""
            mock_run.return_value = mock_process
            
            # Execute the script
            result = runner.execute(name, args)
            
            # Verify the result
            assert result["success"] == True, f"Script {name} execution should succeed"
            assert result["output"] == "Mock output", f"Script {name} output should match mock"
            assert result["command"] == name, f"Command should be {name}"
            assert result["args"] == [], f"Args should be empty list (script runner ignores them)"
            
            # Verify subprocess.run was called correctly
            mock_run.assert_called_once_with([path], capture_output=True, text=True, check=True)
    finally:
        # Clean up temporary file
        if os.path.exists(path):
            os.unlink(path)

# Test unauthorized script execution
@given(
    valid_script=script_files(),
    unauthorized_name=script_names()
)
def test_unauthorized_script_execution(valid_script, unauthorized_name):
    """Test executing an unauthorized script"""
    name, path, _, hash_val = valid_script
    
    try:
        # Skip if the unauthorized name happens to match the valid one
        assume(unauthorized_name != name)
        
        # Initialize ScriptRunner with a valid script
        runner = ScriptRunner({name: path}, {name: hash_val})
        
        # Try to execute an unauthorized script
        result = runner.execute(unauthorized_name)
        
        # Verify the result
        assert result["success"] == False, "Unauthorized script execution should fail"
        assert "Unauthorized script" in result["error"], "Error should indicate unauthorized script"
    finally:
        # Clean up temporary file
        if os.path.exists(path):
            os.unlink(path)

# Test script execution with error
@given(script=script_files())
@settings(max_examples=25)
def test_script_execution_error(script):
    """Test script execution with error"""
    name, path, _, hash_val = script
    
    try:
        # Initialize ScriptRunner with the script
        runner = ScriptRunner({name: path}, {name: hash_val})
        
        # Mock subprocess.run to simulate an error
        with patch('subprocess.run') as mock_run:
            # Configure the mock to raise an exception
            mock_run.side_effect = Exception("Mocked execution error")
            
            # Execute the script
            result = runner.execute(name)
            
            # Verify the result
            assert result["success"] == False, f"Script {name} execution should fail"
            assert "Mocked execution error" in result["error"], "Error should contain exception message"
    finally:
        # Clean up temporary file
        if os.path.exists(path):
            os.unlink(path)

# Test async script execution
@pytest.mark.asyncio
@given(script=script_files())
@settings(max_examples=25)
async def test_async_script_execution(script):
    """Test asynchronous script execution"""
    name, path, _, hash_val = script
    
    try:
        # Initialize ScriptRunner with the script
        runner = ScriptRunner({name: path}, {name: hash_val})
        
        # Mock the execute method to avoid actually running the script
        with patch.object(runner, 'execute') as mock_execute:
            # Configure the mock
            mock_execute.return_value = {
                "success": True,
                "output": "Mock async output",
                "error": "",
                "command": name,
                "args": []
            }
            
            # Execute the script asynchronously
            result = await runner.execute_async(name)
            
            # Verify the result
            assert result["success"] == True, f"Async script {name} execution should succeed"
            assert result["output"] == "Mock async output", f"Script {name} output should match mock"
            
            # Verify execute was called correctly
            mock_execute.assert_called_once_with(name, None)
    finally:
        # Clean up temporary file
        if os.path.exists(path):
            os.unlink(path)

# Stateful testing with RuleBasedStateMachine
class ScriptRunnerStateMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.temp_dir = tempfile.mkdtemp()
        self.runner = ScriptRunner({})
        self.registered_scripts = {}
        self.script_hashes = {}
    
    @rule(script=script_files())
    def register_script(self, script):
        """Register a script and verify it was registered correctly"""
        name, path, content, hash_val = script
        
        # Copy the script to our temp directory to avoid file cleanup issues
        new_path = os.path.join(self.temp_dir, f"{name}_{hash_val[:8]}.sh")
        shutil.copy(path, new_path)
        os.chmod(new_path, 0o755)
        
        # Register the script
        result = self.runner.register_script(name, new_path)
        
        if name in self.registered_scripts:
            # Should fail for duplicate names
            assert result is False, f"Duplicate script {name} registration should fail"
            # Original path should not be changed
            assert self.runner.allowed_scripts[name] == os.path.abspath(self.registered_scripts[name]), \
                f"Original script path should not be overwritten"
        else:
            # Should succeed for new scripts
            assert result is True, f"Script {name} registration should succeed"
            assert name in self.runner.allowed_scripts, f"Script {name} should be in allowed_scripts"
            assert os.path.abspath(new_path) == self.runner.allowed_scripts[name], f"Script path should match"
            
            # Store the script info for newly registered scripts
            self.registered_scripts[name] = new_path
            self.script_hashes[name] = hash_val
    
    @rule(name=script_names())
    def verify_script_integrity(self, name):
        """Verify script integrity"""
        if name in self.registered_scripts:
            # Should pass for registered scripts
            assert self.runner.verify_script_integrity(name), f"Script {name} should pass integrity check"
        else:
            # Should fail for unknown scripts
            assert not self.runner.verify_script_integrity(name), f"Unknown script {name} should fail integrity check"
    
    @rule(name=script_names(), args=script_arguments())
    def execute_script(self, name, args):
        """Execute a script"""
        # Mock subprocess.run to avoid actually running the script
        with patch('subprocess.run') as mock_run:
            # Configure the mock
            mock_process = MagicMock()
            mock_process.stdout = "Mock output"
            mock_process.stderr = ""
            mock_run.return_value = mock_process
            
            # Execute the script
            result = self.runner.execute(name, args)
            
            if name in self.registered_scripts:
                # Should succeed for registered scripts
                assert result["success"] == True, f"Script {name} execution should succeed"
                assert result["output"] == "Mock output", f"Script {name} output should match mock"
                # Verify subprocess.run was called correctly
                mock_run.assert_called_once_with(
                    [self.runner.allowed_scripts[name]], 
                    capture_output=True, 
                    text=True, 
                    check=True
                )
            else:
                # Should fail for unknown scripts
                assert result["success"] == False, f"Unknown script {name} execution should fail"
                assert "Unauthorized script" in result["error"], "Error should indicate unauthorized script"
    
    @invariant()
    def registered_scripts_are_consistent(self):
        """Verify that registered scripts are consistent"""
        for name, path in self.registered_scripts.items():
            assert name in self.runner.allowed_scripts, f"Script {name} should be in allowed_scripts"
            assert os.path.abspath(path) == self.runner.allowed_scripts[name], f"Script path should match"
    
    def teardown(self):
        """Clean up temporary files"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

# Run the state machine test
TestScriptRunnerStateMachine = ScriptRunnerStateMachine.TestCase