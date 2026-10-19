// Presets as pictures in the shot form: the camera moves as clips, the move a
// whole camera line starts with shown as picked.
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CameraField } from "../src/components/ShotForm";
import type { Api } from "../src/api";
import { setApi } from "../src/host";
import { initialState, store } from "../src/store";
import type { PresetList } from "../src/types";

setApi({ presetImageUrl: (name: string) => `/seriesmith/presets/image?name=${name}` } as unknown as Api);

const PRESETS: PresetList = {
  relight: [], look: [], look_builder: [],
  framing: [{ id: "cu", label: "Close-up", group: "close", hint: "the face", image: "framing/cu.jpg" }],
  camera: [
    { id: "push_in", label: "Push in", group: "dolly", move: "pushes in", image: "camera/push_in.mp4" },
    { id: "pan_left", label: "Pan left", group: "pivot", move: "pans left" },
  ],
};

describe("the shot form's presets", () => {
  it("offers the camera moves as clips, the line's own move picked", () => {
    store.set({ ...initialState(), presets: PRESETS });
    const html = renderToString(createElement(CameraField, { value: "pushes in with small amplitude at slow speed", onChange: () => {} }));
    expect(html).toContain("Camera moves, as clips");
    expect(html).toContain("· <!-- -->Push in");          // picked: the move the line starts with
    expect(html).not.toContain("Pan left");                // folded away once a move is set
  });

  it("starts open on an empty line", () => {
    store.set({ ...initialState(), presets: PRESETS });
    const html = renderToString(createElement(CameraField, { value: "", onChange: () => {} }));
    expect(html).toContain("Pan left");
    expect(html).toContain("Pan and tilt");                // grouped
    expect(html).toContain("camera/push_in.mp4");          // a sample clip, played on hover
    expect(html).toContain("<video");
  });
});
