"""Run one of seriesmith's own modules as `python -m seriesmith.<module>` would, with the
folder holding the package on sys.path: `python <this file> seriesmith.assemble args...`.

`python -m` alone isn't enough under an embedded Python whose ._pth file fixes sys.path
(ComfyUI's python_embeded), where PYTHONPATH is ignored too; edit.tool_cmd runs the pipeline's
tools (build, assemble, publish, align, kreagen, mksheet) through this file instead. Only a
module of the seriesmith package runs, named by its dotted name."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# this file's own folder is sys.path[0] when it's run by path: off it, or seriesmith/queue.py
# would stand in for the standard library's queue
sys.path[:] = [p for p in sys.path if os.path.normcase(os.path.abspath(p or ".")) != os.path.normcase(HERE)]
sys.path.insert(0, os.path.dirname(HERE))


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    parts = name.split(".")
    if parts[0] != "seriesmith" or len(parts) < 2 or not all(p.isidentifier() for p in parts):
        sys.exit("usage: python _run.py seriesmith.<module> [args...]")
    import runpy
    sys.argv = [name] + sys.argv[2:]
    runpy.run_module(name, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
