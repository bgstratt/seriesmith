# seriesmith

A series config and episode scripts in, finished episodes out.

You describe a show once in `series.json` (the cast, the places, the voices, the
look) and write episodes as screenplay-flavoured scripts (`epNN.md`). seriesmith
breaks each episode into shots, writes every shot's prompt for the model that
renders it, and keeps characters and locations consistent across the whole
series.

Any shot can render on any model it suits: MiniMax H3, LTX-2 or Wan on your own
GPU through ComfyUI, or hosted models such as Seedance and Kling through Comfy's
cloud. The plan is in [docs/DESIGN.md](docs/DESIGN.md).

seriesmith is the successor to h3pipe and is being ported from it step by step.
Today it compiles: script and series config to the story and to each target's
shotlist. Rendering, the editor and the finishing stages come next.

## Try it

Python 3.10 or newer.

    pip install -e .
    seriesmith check examples/series_example.json examples/script_example.md
    seriesmith build examples/series_example.json examples/script_example.md -o out

`build` writes `out/shotlist/` (the story as `shots.json`, and a shotlist per
target) and `out/refs_todo.md`, the reference pictures the episode still needs.
`check` reports the same without writing anything; `--pace` checks whether each
line of dialogue fits its shot.

Without installing, `python -m seriesmith` does the same from the repo folder.

## Tests

    python -m pytest

The golden tests rebuild every fixture and compare the results byte for byte
with `tests/golden/`.

## License

MIT — see [LICENSE](LICENSE).
