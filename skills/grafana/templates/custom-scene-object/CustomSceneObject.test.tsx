import { activateFullSceneTree } from "@grafana/scenes";
import { CustomSceneObject } from "./CustomSceneObject";

describe("CustomSceneObject", () => {
  it("initializes with empty filter", () => {
    const obj = new CustomSceneObject();
    expect(obj.state.filter).toBe("");
  });

  it("updates filter via onFilterChange", () => {
    const obj = new CustomSceneObject();
    const deactivate = activateFullSceneTree(obj);
    try {
      obj.onFilterChange("hello");
      expect(obj.state.filter).toBe("hello");
    } finally {
      deactivate();
    }
  });

  it("reads from URL on update", () => {
    const obj = new CustomSceneObject();
    obj.updateFromUrl({ filter: "urlValue" });
    expect(obj.state.filter).toBe("urlValue");
  });

  it("writes to URL state", () => {
    const obj = new CustomSceneObject({ filter: "abc" });
    expect(obj.getUrlState()).toEqual({ filter: "abc" });
  });
});
