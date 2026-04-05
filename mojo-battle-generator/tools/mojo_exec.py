"""
Mojo code executor — uruchamia Mojo przez Docker lub symuluje przez Python.
"""
import subprocess
import tempfile
import os
import re


MOJO_DOCKER = "modular/mojo:latest"
USE_DOCKER = True  # False = symulacja przez Python (fallback)


def exec_mojo(code: str, timeout: int = 30) -> dict:
    """
    Wykonuje kod Mojo. Zwraca { stdout, stderr, exit_code, success }.
    """
    if USE_DOCKER:
        return _exec_docker(code, timeout)
    else:
        return _exec_simulated(code, timeout)


def _exec_docker(code: str, timeout: int) -> dict:
    with tempfile.NamedTemporaryFile(suffix='.mojo', mode='w', delete=False) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [
                'docker', 'run', '--rm',
                '--memory', '512m',
                '--cpus', '1',
                '-v', f'{tmp_path}:/code/main.mojo:ro',
                MOJO_DOCKER,
                'mojo', 'run', '/code/main.mojo'
            ],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            'stdout': result.stdout,
            'stderr': result.stderr,
            'exit_code': result.returncode,
            'success': result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {'stdout': '', 'stderr': 'TIMEOUT', 'exit_code': -1, 'success': False}
    except FileNotFoundError:
        # Docker nie zainstalowany — fallback
        return _exec_simulated(code, timeout)
    finally:
        os.unlink(tmp_path)


def _exec_simulated(code: str, timeout: int) -> dict:
    """
    Symuluje wykonanie Mojo przez konwersję podstawowych konstruktów do Pythona.
    Tylko dla prostych przypadków — kompletny fallback.
    """
    py_code = _mojo_to_python_rough(code)
    with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
        f.write(py_code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ['python3', tmp_path],
            capture_output=True, text=True, timeout=timeout
        )
        return {
            'stdout': result.stdout,
            'stderr': result.stderr + ('\n[SIMULATED - not real Mojo]' if result.stderr else '[SIMULATED - not real Mojo]'),
            'exit_code': result.returncode,
            'success': result.returncode == 0,
            'simulated': True
        }
    except subprocess.TimeoutExpired:
        return {'stdout': '', 'stderr': 'TIMEOUT', 'exit_code': -1, 'success': False}
    finally:
        os.unlink(tmp_path)


def _mojo_to_python_rough(mojo: str) -> str:
    """Rough transpilation Mojo → Python dla podstawowych przypadków."""
    py = mojo
    py = re.sub(r'\bfn\s+main\(\)', 'def main():', py)
    py = re.sub(r'\bfn\s+(\w+)\(([^)]*)\)\s*->\s*\w+:', r'def \1(\2):', py)
    py = re.sub(r'\bfn\s+(\w+)\(([^)]*)\):', r'def \1(\2):', py)
    py = re.sub(r'\bvar\s+', '', py)
    py = re.sub(r'\blet\s+', '', py)
    py = re.sub(r':\s*(Int|Float64|String|Bool)\b', '', py)
    py = re.sub(r'print\(', 'print(', py)
    # Dodaj wywołanie main() na końcu
    if 'def main()' in py:
        py += '\nmain()\n'
    return py


def install_docker_mojo():
    """Pobiera obraz Mojo jeśli nie istnieje."""
    result = subprocess.run(
        ['docker', 'pull', MOJO_DOCKER],
        capture_output=True, text=True
    )
    return result.returncode == 0
