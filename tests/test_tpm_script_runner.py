import pytest
from hypothesis import given, strategies as st, assume
from helper.script_runner import ScriptRunner
import tempfile
import os
import hashlib
import asyncio
import string

@given(
    # Generate script names with ASCII-only letters
    scripts=st.dictionaries(
        keys=st.text(min_size=1, max_size=20, alphabet=string.ascii_letters),
        # Use very simple script content that just echoes a message
        values=st.just("echo 'This is a test script'"),
        min_size=1, max_size=5
    ),
    # Generate a script name that doesn't exist
    nonexistent_script=st.text(min_size=1, max_size=20, alphabet=string.ascii_letters),
    # Generate simple args
    args=st.lists(st.text(min_size=0, max_size=20, alphabet=string.ascii_letters), min_size=0, max_size=3)
)
def test_script_runner_integrity_verification(scripts, nonexistent_script, args):
    """Test ScriptRunner's script integrity verification with various scripts and hashes"""
    # Create temporary script files
    script_paths = {}
    script_hashes = {}
    modified_scripts = {}
    
    try:
        # Make sure nonexistent_script is not in our scripts dictionary
        assume(nonexistent_script not in scripts)
        
        # Create script files and calculate hashes
        for name, content in scripts.items():
            with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.sh') as f:
                # Create a very simple shell script
                script_content = "#!/bin/sh\n" + content
                f.write(script_content)
                script_paths[name] = f.name
                # Make executable
                os.chmod(f.name, 0o755)
                # Calculate hash
                script_hashes[name] = hashlib.sha256(script_content.encode()).hexdigest()
            
            # Create a modified version of the script for tampering tests
            modified_content = script_content + "\necho 'This script has been tampered with'"
            modified_scripts[name] = modified_content
        
        # 1. Test with correct hashes
        runner = ScriptRunner(script_paths, script_hashes)
        
        # Verify all scripts pass integrity check
        for name in scripts.keys():
            assert runner.verify_script_integrity(name), f"Script {name} should pass integrity check"
        
        # Execute each script
        for name in scripts.keys():
            result = runner.execute(name, [])
            # Print debugging info if execution fails
            if not result["success"]:
                print(f"Script execution failed for {name}")
                print(f"Error: {result.get('error', 'No error message')}")
                print(f"Output: {result.get('output', 'No output')}")
                print(f"Return code: {result.get('returncode', 'No return code')}")
                # Check if file exists and is executable
                if not os.path.exists(script_paths[name]):
                    print(f"Script file does not exist: {script_paths[name]}")
                elif not os.access(script_paths[name], os.X_OK):
                    print(f"Script file is not executable: {script_paths[name]}")
                
            assert result["success"], f"Script {name} should execute successfully with valid hash"
            assert result["command"] == name, "Result should contain correct command name"
        
        # 2. Test with tampered scripts
        for name, content in modified_scripts.items():
            # Modify the script file
            with open(script_paths[name], 'w') as f:
                f.write(content)
            
            # Verify script fails integrity check
            assert not runner.verify_script_integrity(name), f"Tampered script {name} should fail integrity check"
            
            # Attempt to execute should fail
            result = runner.execute(name, [])
            assert not result["success"], f"Tampered script {name} should fail to execute"
            assert "integrity check failed" in result["error"], "Error should mention integrity check"
        
        # 3. Test with nonexistent script
        assert not runner.verify_script_integrity(nonexistent_script), "Nonexistent script should fail verification"
        result = runner.execute(nonexistent_script, [])
        assert not result["success"], "Nonexistent script should fail to execute"
        assert "Unauthorized script" in result["error"], "Error should mention unauthorized script"
        
    finally:
        # Clean up temporary files
        for path in script_paths.values():
            try:
                os.unlink(path)
            except:
                pass

@given(
    # Generate scripts with varied content sizes
    script_contents=st.lists(
        st.text(min_size=1, max_size=1000),
        min_size=2, max_size=5
    ),
    # Generate script names
    script_names=st.lists(
        st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L',))),
        min_size=2, max_size=5,
        unique=True
    )
)
def test_script_runner_registration(script_contents, script_names):
    """Test ScriptRunner's script registration functionality"""
    assume(len(script_names) == len(script_contents))
    
    script_paths = {}
    
    try:
        # Create script files
        for i, (name, content) in enumerate(zip(script_names, script_contents)):
            with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.sh') as f:
                f.write(content)
                script_paths[name] = f.name
                os.chmod(f.name, 0o755)
        
        # Create ScriptRunner without providing hashes
        runner = ScriptRunner(script_paths)
        
        # Check that hashes were automatically calculated
        for name in script_names:
            assert name in runner.script_hashes, f"Hash should be auto-calculated for {name}"
            
            # Verify the calculated hash matches what we'd expect
            with open(script_paths[name], 'rb') as f:
                content = f.read()
            expected_hash = hashlib.sha256(content).hexdigest()
            assert runner.script_hashes[name] == expected_hash, f"Auto-calculated hash for {name} should be correct"
        
        # Try to register a script with a duplicate name (should fail)
        first_script = script_names[0]
        result = runner.register_script(first_script, script_paths[script_names[1]])
        assert not result, "Registering a duplicate script should fail"
        
        # Try registering a nonexistent file (should fail)
        nonexistent_path = "/path/to/nonexistent/script.sh"
        result = runner.register_script("nonexistent", nonexistent_path)
        assert not result, "Registering a nonexistent script should fail"
        
    finally:
        # Clean up temporary files
        for path in script_paths.values():
            try:
                os.unlink(path)
            except:
                pass


@given(
    # Generate a list of script contents with predictable exit codes
    script_exit_codes=st.lists(
        st.integers(min_value=0, max_value=5),
        min_size=3, max_size=5
    )
)
def test_script_runner_execution_results(script_exit_codes):
    """Test ScriptRunner's handling of different script execution results"""
    script_paths = {}
    script_names = []
    
    try:
        # Create scripts that exit with different status codes
        for i, exit_code in enumerate(script_exit_codes):
            script_name = f"script_{i}"
            script_names.append(script_name)
            
            # Create script content that exits with the specified code
            script_content = f"""#!/bin/sh
echo "This is script {i} with exit code {exit_code}"
echo "Error message for script {i}" >&2
exit {exit_code}
"""
            # Write script to file
            with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.sh') as f:
                f.write(script_content)
                script_paths[script_name] = f.name
                os.chmod(f.name, 0o755)
        
        # Create ScriptRunner
        runner = ScriptRunner(script_paths)
        
        # Test executing each script
        for i, script_name in enumerate(script_names):
            exit_code = script_exit_codes[i]
            result = runner.execute(script_name)
            
            # Check result structure
            assert "success" in result, "Result should include success field"
            assert "output" in result, "Result should include output field"
            assert "error" in result, "Result should include error field"
            assert "command" in result, "Result should include command field"
            assert "args" in result, "Result should include args field"
            
            # Check success status based on exit code
            if exit_code == 0:
                assert result["success"], "Script with exit code 0 should be successful"
            else:
                assert not result["success"], f"Script with exit code {exit_code} should not be successful"
                assert "returncode" in result, "Failed execution should include returncode"
                assert result["returncode"] == exit_code, "Returncode should match script exit code"
            
            # Verify output and error content
            assert f"This is script {i}" in result["output"], "Output should contain script stdout"
            assert f"Error message for script {i}" in result["error"], "Error should contain script stderr"
            
    finally:
        # Clean up temporary files
        for path in script_paths.values():
            try:
                os.unlink(path)
            except:
                pass