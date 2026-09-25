"""Foundation command; content-processing commands will be added incrementally."""

import argparse

from kenton_workflow import __version__


def main() -> int:
    """Display package help or version without accessing church materials."""
    parser = argparse.ArgumentParser(
        prog="kenton-workflow",
        description="Kenton worship workflow: documentation and project foundation.",
        epilog="Content import, generation, publishing, and archiving are not implemented yet.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args()
    parser.print_help()
    return 0
