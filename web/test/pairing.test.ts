import { describe, expect, it } from "vitest";
import { deviceName } from "../src/lib/pairing";

describe("a paired device's name", () => {
  it("says the browser and the system", () => {
    expect(deviceName("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"))
      .toBe("Chrome on Windows");
    expect(deviceName("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"))
      .toBe("Safari on iPhone");
    expect(deviceName("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36 Edg/140.0"))
      .toBe("Edge on Mac");
    expect(deviceName("curl/8.0")).toBe("A browser");
  });
});
