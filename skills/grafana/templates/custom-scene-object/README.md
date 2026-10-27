# Custom scene object template

A reusable `SceneObjectBase` subclass with:

- Typed state interface
- Public methods used from the renderer
- Activation handler with cleanup
- URL sync for one state key
- Companion test file

## Files

- `CustomSceneObject.tsx` — class + renderer
- `CustomSceneObject.test.tsx` — Jest tests using `activateFullSceneTree`

## Anatomy

```tsx
class CustomSceneObject extends SceneObjectBase<State> {
  static Component = Renderer;       // Required — React component
  protected _urlSync = ...;          // Optional — URL sync
  constructor(state) {               // Always merge defaults with partial
    super({ ...defaults, ...state });
    this.addActivationHandler(this._onActivate);
  }
  private _onActivate = () => {      // Subscribe + return cleanup
    const sub = ...;
    return () => sub.unsubscribe();
  };
  getUrlState() { ... }              // Required if using URL sync
  updateFromUrl(values) { ... }      // Required if using URL sync
  // Public methods invoked from renderer:
  onSomething = (...) => { this.setState({ ... }); };
}
```

## When to use this template

- A new control widget for `EmbeddedScene.controls`.
- A custom panel-like component (use `<scene.Component model={obj} />` to render).
- A controller object that orchestrates state across multiple panels.

If you only need to drop a stateless React node into a scene, use `SceneReactObject` instead — much simpler.

## Common variants

### As a control in EmbeddedScene

```ts
new EmbeddedScene({
  controls: [new CustomSceneObject({ placeholder: 'Filter rooms' })],
  body: ...,
});
```

### Driving a query runner

```ts
const filter = new CustomSceneObject();
const queryRunner = new SceneQueryRunner({...});

queryRunner.addActivationHandler(() => {
  const sub = filter.subscribeToState(({ filter: f }) => {
    queryRunner.setState({
      queries: [{ ...queryRunner.state.queries[0], expr: `up{name=~"${f}.*"}` }],
    });
    queryRunner.runQueries();
  });
  return () => sub.unsubscribe();
});
```

### As a behavior (no UI)

If you don't need to render anything, just remove the `static Component = ...` (it defaults to a null-render) and attach via `$behaviors: [...]` instead of as a child.

## Pitfalls

- **No `parent` in the constructor** — set in tree assembly. Look up via `sceneGraph.*` inside `_onActivate`.
- **Always return cleanup** from activation handlers if you subscribe.
- **`setState` mutates immutably** — `this.setState({ list: [...this.state.list, item] })`, not `.push()`.
