"""
The editor's server, in two hosts (docs/DESIGN.md, "The editor, in two hosts"):

    standalone.py   `seriesmith serve`: seriesmith's own aiohttp server, the
                    editor's page, its API and an event websocket
    comfyui.py      the same API registered on ComfyUI's server, loaded by
                    seriesmith's node pack
    views.py        the API (seriesmith.api) as aiohttp views, for either
"""
