"""Build the standalone upgrade stop helper with MSVC's static CRT (/MT)."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(output):
    if sys.platform != 'win32':
        raise RuntimeError('The native stop helper must be compiled on Windows with MSVC 2022.')
    output = Path(output).resolve()
    source = ROOT / 'packaging/windows_stop.cpp'
    project = ROOT / 'build/windows-stop-project'
    project.mkdir(parents=True, exist_ok=True)
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.21)
cmake_policy(SET CMP0091 NEW)
project(citrica_stop LANGUAGES CXX)
add_executable(citrica-stop "{source.as_posix()}")
target_compile_features(citrica-stop PRIVATE cxx_std_17)
set_property(TARGET citrica-stop PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
target_compile_options(citrica-stop PRIVATE /O2 /W4 /WX /utf-8 /permissive-)
target_link_libraries(citrica-stop PRIVATE bcrypt pathcch)
target_link_options(citrica-stop PRIVATE /DYNAMICBASE /NXCOMPAT)
''', encoding='utf-8')
    binary = ROOT / 'build/windows-stop-cmake'
    subprocess.run(['cmake', '-S', str(project), '-B', str(binary), '-G', 'Visual Studio 17 2022', '-A', 'x64'], check=True)
    subprocess.run(['cmake', '--build', str(binary), '--config', 'Release', '--parallel', '2'], check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary / 'Release/citrica-stop.exe', output)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/windows-package/citrica-stop.exe')
    args = parser.parse_args()
    print(build(args.output))
