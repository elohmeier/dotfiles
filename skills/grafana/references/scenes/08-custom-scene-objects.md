# Custom scene objects

Build your own `SceneObjectBase` subclass when you need custom UI, custom logic that integrates with the scene graph, or both.

## When to build a custom scene object

- A widget you want in `controls` (e.g., a custom filter input).
- A panel-like component that doesn't fit `VizPanel` (e.g., a custom card grid).
- A controller object that orchestrates state across multiple panels.
- A behavior that needs its own state (use a stateless function instead if it doesn't).

If you just need to render React inside a scene without the full scene-object machinery, use `SceneReactObject` (covered below).

## The basic shape

```tsx
// CustomFilter.tsx
import {
  SceneComponentProps,
  sceneGraph,
  SceneObjectBase,
  SceneObjectState,
  SceneObjectUrlSyncConfig,
  SceneObjectUrlValues,
} from "@grafana/scenes";
import { Input } from "@grafana/ui";
import React from "react";

interface CustomFilterState extends SceneObjectState {
  filter: string;
  placeholder?: string;
}

export class CustomFilter extends SceneObjectBase<CustomFilterState> {
  public static Component = CustomFilterRenderer;

  // Opt into URL sync
  protected _urlSync = new SceneObjectUrlSyncConfig(this, {
    keys: () => ["filter"],
  });

  public constructor(state: Partial<CustomFilterState> = {}) {
    super({
      filter: "",
      placeholder: "Search...",
      ...state,
    });

    this.addActivationHandler(this._onActivate);
  }

  private _onActivate = () => {
    // Subscribe to time range, variables, etc. if needed
    // Return a deactivation handler
  };

  // URL sync helpers
  public getUrlState(): SceneObjectUrlValues {
    return { filter: this.state.filter };
  }

  public updateFromUrl(values: SceneObjectUrlValues) {
    if (
      typeof values.filter === "string" && values.filter !== this.state.filter
    ) {
      this.setState({ filter: values.filter });
    }
  }

  // Public methods called from the renderer
  public onFilterChange = (filter: string) => {
    this.setState({ filter });
  };
}

function CustomFilterRenderer({ model }: SceneComponentProps<CustomFilter>) {
  const { filter, placeholder } = model.useState();

  return (
    <Input
      value={filter}
      placeholder={placeholder}
      onChange={(e) => model.onFilterChange(e.currentTarget.value)}
    />
  );
}
```

## State design

- Keep state **flat and serializable**. Only state participates in `useState()` reactivity.
- Don't store React refs, DOM nodes, or unsubscribers in state. Store them as private class fields.
- Default values go in the constructor `super({ ... })` call.
- Make state fields optional and provide sensible defaults rather than forcing every consumer to pass everything.

## Activation handlers

`addActivationHandler` accepts a function called when the renderer mounts. Use it for:

- Subscribing to other scene objects.
- Kicking off async work.
- Wiring up reactions to time range / variable / data changes.

```ts
this.addActivationHandler(() => {
  const variables = sceneGraph.getVariables(this);
  const cluster = variables.getByName("cluster");

  const sub = cluster?.subscribeToState(() => {
    this.recompute();
  });

  return () => sub?.unsubscribe();
});
```

You can register **multiple** activation handlers; they all run on activation, and their returned cleanup functions all run on deactivation.

## Reading scene context

From inside any method (after the object is in the tree), use `sceneGraph`:

```ts
public computeQueryUrl(): string {
  const variables = sceneGraph.getVariables(this);
  const timeRange = sceneGraph.getTimeRange(this).state.value;
  const interpolated = sceneGraph.interpolate(this, '${cluster:csv}');
  return `/api/data?cluster=${encodeURIComponent(interpolated)}&from=${timeRange.from.valueOf()}`;
}
```

## URL sync (the long form)

For deeper URL sync needs, the `SceneObjectUrlSyncConfig` accepts callbacks:

```ts
import { SceneObjectUrlSyncConfig } from '@grafana/scenes';

protected _urlSync = new SceneObjectUrlSyncConfig(this, {
  keys: () => ['filter', 'sort'],          // URL keys this object owns
  getUrlState: () => ({                     // Called to write state to URL
    filter: this.state.filter,
    sort: this.state.sort,
  }),
  updateFromUrl: (values) => {              // Called when URL changes
    const partial: Partial<CustomFilterState> = {};
    if (typeof values.filter === 'string') partial.filter = values.filter;
    if (typeof values.sort === 'string') partial.sort = values.sort as 'asc' | 'desc';
    if (Object.keys(partial).length) this.setState(partial);
  },
});
```

If you implement `getUrlState` and `updateFromUrl` directly on the class (matching method names), you can use the short form `new SceneObjectUrlSyncConfig(this, { keys: [...] })`.

## SceneReactObject — drop in a React component

When you don't need state/lifecycle of your own:

```ts
import { SceneReactObject } from "@grafana/scenes";

new SceneReactObject({
  reactNode: (
    <Card>
      <Card.Heading>Hello</Card.Heading>
    </Card>
  ),
});

// Or render a component that receives no props:
new SceneReactObject({
  component: () => <div>Hello</div>,
});
```

Use cases: title cards, status badges, links, anywhere a simple non-reactive bit of React makes sense.

## Updating other objects

A custom controller object can mutate panels and layouts as state changes:

```ts
export class FilterController extends SceneObjectBase<{ filter: string }> {
  constructor() {
    super({ filter: "" });
    this.addActivationHandler(() => {
      const sub = this.subscribeToState(({ filter }) => {
        this.applyFilter(filter);
      });
      return () => sub.unsubscribe();
    });
  }

  private applyFilter(filter: string) {
    const grid = sceneGraph.findObject(
      this.parent!,
      (o) => o.state.key === "main-grid",
    );
    if (!grid || !("children" in grid.state)) return;

    const children = (grid.state.children as SceneObject[]).filter((child) => {
      // some filtering logic
      return matches(child, filter);
    });

    grid.setState({ children });
  }
}
```

## Combining with PanelBuilders.behaviors

Pass your custom object as a `$behaviors` entry to attach it to another scene object:

```ts
PanelBuilders.timeseries()
  .setBehaviors([new MyPanelDecorator({ ... })])
  .build();
```

The decorator's `parent` will be the panel, and you can read/write the panel's state.

## Testing custom objects

```ts
// Activate manually for unit tests:
const obj = new CustomFilter({ filter: "foo" });
const deactivate = activateFullSceneTree(obj); // helper from @grafana/scenes/utils

// Test:
obj.onFilterChange("bar");
expect(obj.state.filter).toBe("bar");

// Cleanup:
deactivate();
```

`activateFullSceneTree` is the standard way to drive a scene tree without rendering React.

## Anti-patterns

- **Storing the parent reference at construction time.** `this.parent` is `undefined` until the object is added to a parent's state — and it's not stable until activation. Look it up at use time.
- **Side effects in the constructor.** Use the activation handler. Constructors should only set initial state.
- **Mutating `this.state` directly.** Always call `this.setState({ ... })`. Mutation will not trigger reactivity.
- **Long-lived subscriptions without cleanup.** If you `subscribe` to anything, return an unsubscribe from the activation handler.
- **Re-rendering by changing keys.** Avoid changing `state.key` after the object exists; React reconciliation depends on it.
