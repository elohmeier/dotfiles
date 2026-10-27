import {
  SceneComponentProps,
  sceneGraph,
  SceneObjectBase,
  SceneObjectState,
  SceneObjectUrlSyncConfig,
  SceneObjectUrlValues,
} from "@grafana/scenes";
import { Field, Input } from "@grafana/ui";
import React from "react";

interface CustomSceneObjectState extends SceneObjectState {
  // Public state — flat, serializable, participates in useState() reactivity.
  filter: string;
  placeholder?: string;
}

export class CustomSceneObject extends SceneObjectBase<CustomSceneObjectState> {
  public static Component = CustomSceneObjectRenderer;

  // URL sync — keys this object owns. Implement getUrlState/updateFromUrl below.
  protected _urlSync = new SceneObjectUrlSyncConfig(this, {
    keys: () => ["filter"],
  });

  public constructor(state: Partial<CustomSceneObjectState> = {}) {
    super({
      filter: "",
      placeholder: "Search...",
      ...state,
    });

    this.addActivationHandler(this._onActivate);
  }

  // Activation — runs when renderer mounts. Return cleanup if subscribing.
  private _onActivate = () => {
    // Example: react to time range changes
    const timeRange = sceneGraph.getTimeRange(this);
    const sub = timeRange.subscribeToState(() => {
      // Do something when time range changes
    });

    return () => sub.unsubscribe();
  };

  // URL sync — write state to URL.
  public getUrlState(): SceneObjectUrlValues {
    return { filter: this.state.filter };
  }

  // URL sync — read state from URL on init / browser nav.
  public updateFromUrl(values: SceneObjectUrlValues) {
    if (typeof values.filter === "string" && values.filter !== this.state.filter) {
      this.setState({ filter: values.filter });
    }
  }

  // Public methods called from the renderer.
  public onFilterChange = (filter: string) => {
    this.setState({ filter });
  };

  public clear = () => {
    this.setState({ filter: "" });
  };
}

function CustomSceneObjectRenderer({ model }: SceneComponentProps<CustomSceneObject>) {
  // useState subscribes — component re-renders on state change.
  const { filter, placeholder } = model.useState();

  return (
    <Field label="Filter">
      <Input
        value={filter}
        placeholder={placeholder}
        onChange={(e) => model.onFilterChange(e.currentTarget.value)}
      />
    </Field>
  );
}
