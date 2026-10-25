"""Test-only latency wrapper; delegates requests to the actual configured engine."""
import json
import os
import sys
import time
from pathlib import Path

command = json.loads(sys.argv[1])
marker = Path(sys.argv[2])
marker.write_text('started')
time.sleep(1)
os.execv(command[0], [*command, *sys.argv[3:]])
