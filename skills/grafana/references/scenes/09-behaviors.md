# Behaviors

Behaviors are scene objects (or stateless functions) attached to other scene objects via `$behaviors`. They run when their parent activates, optionally subscribe to state changes, and clean up when their parent deactivates.

Use behaviors for **side effects** that don't render UI: cross-panel sync, variable-driven side effects, telemetry, auto-refresh, conditional visibility.

## Attaching behaviors

```ts
new VizPanel({
  pluginId: "timeseries",
  title: "CPU",
  $behaviors: [
    new behaviors.LiveNowTimer({ enabled: true }),
    new behaviors.ActWhenVariableChanged({
      variableName: "host",
      onChange: (v) => {},
    }),
    statelessLoggerBehavior,
  ],
  $data: queryRunner,
});
```

Any scene object can host `$behaviors`: panels, query runners, layouts, the `EmbeddedScene` itself.

## Stateless function behaviors

Simplest form: a function `(parent: SceneObject) => CancelActivationHandler | void`.

```ts
import { SceneObject } from '@grafana/scenes';

const StatelessLogger = (parent: SceneObject) => {
  console.log(`${parent.state.key} activated`);

  const sub = parent.subscribeToState(() => {
    console.log(`${parent.state.key} changed`);
  });

  return () => {
    sub.unsubscribe();
    console.log(`${parent.state.key} deactivated`);
  };
};

new VizPanel({ ..., $behaviors: [StatelessLogger] });
```

The function runs on parent activation, returns an optional cleanup invoked on deactivation.

## Stateful (scene object) behaviors

When a behavior needs configuration:

```tsx
import {
  SceneObject,
  SceneObjectBase,
  SceneObjectState,
} from "@grafana/scenes";

interface AutoRefreshState extends SceneObjectState {
  intervalMs: number;
  enabled: boolean;
}

export class AutoRefresh extends SceneObjectBase<AutoRefreshState> {
  private _timer?: ReturnType<typeof setInterval>;

  constructor(state: Partial<AutoRefreshState> = {}) {
    super({ intervalMs: 30_000, enabled: true, ...state });
    this.addActivationHandler(this._onActivate);
  }

  private _onActivate = () => {
    const parent = this.parent;
    if (!parent) return;

    const tick = () => {
      // Trigger a refresh on the parent if it's a query runner
      if ("runQueries" in parent && typeof parent.runQueries === "function") {
        (parent as any).runQueries();
      }
    };

    if (this.state.enabled) {
      this._timer = setInterval(tick, this.state.intervalMs);
    }

    return () => {
      if (this._timer) clearInterval(this._timer);
    };
  };
}
```

Stateful behaviors render no UI — `static Component` returns `null` by default for `SceneObjectBase` subclasses.

## Built-in behaviors

### `ActWhenVariableChanged`

Fire a callback when a named variable's value changes.

```ts
import { behaviors, MultiValueVariable } from "@grafana/scenes";

new behaviors.ActWhenVariableChanged({
  variableName: "cluster",
  onChange: (variable, behavior) => {
    if (!(variable instanceof MultiValueVariable)) return;
    const cluster = variable.state.value;
    console.log("cluster ->", cluster);
    // Optional cleanup:
    return () => {/* cleanup */};
  },
});
```

### `CursorSync`

Synchronizes cursor/tooltip across panels in the same scene.

```ts
import { DashboardCursorSync } from '@grafana/data';

new EmbeddedScene({
  $behaviors: [
    new behaviors.CursorSync({
      key: 'cursor-scope-1',
      sync: DashboardCursorSync.Crosshair,    // or .Tooltip or .Off
    }),
  ],
  body: ...,
});
```

Attach `CursorSync` at the level you want shared (the whole scene, or a sub-tree). All panels under it share the cursor scope.

### `LiveNowTimer`

Continuously refreshes the time range when `to=now`. Mimics dashboard "live" mode.

```ts
new EmbeddedScene({
  $behaviors: [new behaviors.LiveNowTimer({ enabled: true })],
  $timeRange: new SceneTimeRange({ from: 'now-5m', to: 'now' }),
  ...
});
```

Methods:

```ts
liveNowTimer.enable();
liveNowTimer.disable();
```

### `SceneQueryStateControllerLike` / `SceneQueryController`

For coordinating query lifecycle — pausing, batching, telemetry. Usually you don't construct these directly; the scene framework wires up a query controller per scene.

If you want to instrument or override:

```ts
import { SceneQueryController } from '@grafana/scenes';

new EmbeddedScene({
  $behaviors: [new SceneQueryController()],
  ...
});
```

## Common patterns

### Toggle visibility based on a variable

```ts
const detailsPanel = new SceneFlexItem({ body: ..., isHidden: false });

const toggle = new behaviors.ActWhenVariableChanged({
  variableName: 'showDetails',
  onChange: (variable) => {
    detailsPanel.setState({ isHidden: variable.getValue() !== 'true' });
  },
});

new EmbeddedScene({
  $variables: ...,
  $behaviors: [toggle],
  body: new SceneFlexLayout({ children: [detailsPanel] }),
});
```

### Telemetry: track time range changes

```ts
const trackTime: SceneStatelessBehavior = (parent) => {
  const timeRange = sceneGraph.getTimeRange(parent);
  const sub = timeRange.subscribeToState(({ value }) => {
    trackEvent("time_range_changed", {
      from: value.from.valueOf(),
      to: value.to.valueOf(),
    });
  });
  return () => sub.unsubscribe();
};
```

### Dynamic queries based on parent variable

```ts
class ParametrizedQuery extends SceneObjectBase<{}> {
  constructor() {
    super({});
    this.addActivationHandler(this._onActivate);
  }

  private _onActivate = () => {
    const parent = this.parent as SceneQueryRunner;
    const variables = sceneGraph.getVariables(this);
    const cluster = variables.getByName('cluster');

    const update = () => {
      const expr = `up{cluster="${cluster?.getValue()}"}`;
      parent.setState({
        queries: [{ ...parent.state.queries[0], expr }],
      });
      parent.runQueries();
    };

    update();
    const sub = cluster?.subscribeToState(update);
    return () => sub?.unsubscribe();
  };
}

new SceneQueryRunner({
  $behaviors: [new ParametrizedQuery()],
  ...
});
```

## When to choose stateless vs stateful

**Stateless function** when:

- The behavior needs no configuration.
- It's a one-off side effect.
- It's a useful utility (logging, telemetry).

**Stateful class** when:

- It has configuration that should be in URL or state.
- It should be inspected/modified at runtime.
- It needs its own complex state (multiple subscribers, batching).

## Cleanup is mandatory

Always return a deactivation handler if you subscribe to anything. Forgotten subscriptions cause memory leaks across navigation. The convention is:

```ts
const _onActivate = () => {
  const subs: Unsubscribable[] = [];

  subs.push(thing1.subscribeToState(...));
  subs.push(thing2.subscribeToState(...));

  return () => subs.forEach((s) => s.unsubscribe());
};
```
