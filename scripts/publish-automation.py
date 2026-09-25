"""Copy the reviewed output into a new local week-set."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _python_environment import ensure_environment
ensure_environment('publish')

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
try:
    from kenton_workflow.automation import main
except ModuleNotFoundError as error:
    print(f"Missing dependency: {error.name}. From the repository, run: python -m pip install -e .")
    raise SystemExit(1)

if __name__ == '__main__':
    raise SystemExit(main('publish'))
