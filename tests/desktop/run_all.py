"""All desktop paths, using one isolated compositor and the same real backend."""
import subprocess
import sys
from pathlib import Path

for script in ['run_flow.py', 'run_stacking.py', 'run_nautilus.py', 'run_actions.py', 'run_settings.py',
               'run_regressions.py', 'run_visual.py']:
    subprocess.run([sys.executable, str(Path(__file__).with_name(script))], check=True)
