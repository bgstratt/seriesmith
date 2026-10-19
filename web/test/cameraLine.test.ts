// A camera line from the builder: the move, its amplitude and speed, and where it goes.
import { describe, expect, it } from "vitest";
import { cameraLine } from "../src/lib/shotForm";

describe("cameraLine", () => {
  it("joins the parts the builder has", () => {
    expect(cameraLine("pushes in", "", "")).toBe("pushes in");
    expect(cameraLine("pushes in", "with small amplitude", "at slow speed")).toBe("pushes in with small amplitude at slow speed");
  });
  it("ends on where the move goes", () => {
    expect(cameraLine("pushes in", "", "at slow speed", "toward her face")).toBe("pushes in at slow speed toward her face");
    expect(cameraLine("pulls out", "with large amplitude", "", "revealing the square")).toBe("pulls out with large amplitude, revealing the square");
    expect(cameraLine("pans right", "", "", "  ")).toBe("pans right");
    expect(cameraLine("tilts down", "", "", "from the rooftops to her")).toBe("tilts down from the rooftops to her");
  });
});
