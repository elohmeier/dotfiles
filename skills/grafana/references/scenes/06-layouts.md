# Layouts

Scenes provides four layout primitives. Pick based on the interaction model you want.

| Layout               | Use when                                                                   |
| -------------------- | -------------------------------------------------------------------------- |
| `SceneFlexLayout`    | Default. Static composition with flexbox. Responsive. Most apps want this. |
| `SceneCSSGridLayout` | Grids of equally-sized panels with auto-fit responsive behavior.           |
| `SceneGridLayout`    | Users need to drag/resize panels (dashboard-style). 24-column grid.        |
| `SplitLayout`        | Two resizable panes with a draggable divider.                              |

## SceneFlexLayout

CSS flexbox under the hood. Compose nested layouts to build complex structures.

```ts
new SceneFlexLayout({
  direction: "column", // 'row' (default) or 'column'
  wrap: "nowrap", // 'wrap' or 'nowrap'
  minHeight: 400,
  children: [
    new SceneFlexItem({
      minHeight: 200,
      body: PanelBuilders.timeseries().setTitle("Top").build(),
    }),
    new SceneFlexItem({
      ySizing: "fill",
      body: new SceneFlexLayout({
        direction: "row",
        children: [
          new SceneFlexItem({ width: "50%", body: leftPanel }),
          new SceneFlexItem({ width: "50%", body: rightPanel }),
        ],
      }),
    }),
  ],
});
```

`SceneFlexItem` and `SceneFlexLayout` both accept the same sizing properties:

```ts
{
  flexGrow?: CSSProperties['flexGrow'];
  alignSelf?: CSSProperties['alignSelf'];
  width?: CSSProperties['width'];          // '50%', 200, '20rem'
  height?: CSSProperties['height'];
  minWidth?: CSSProperties['minWidth'];
  minHeight?: CSSProperties['minHeight'];
  maxWidth?: CSSProperties['maxWidth'];
  maxHeight?: CSSProperties['maxHeight'];
  xSizing?: 'fill' | 'content';            // Width strategy
  ySizing?: 'fill' | 'content';
  isHidden?: boolean;
  md?: SceneFlexItemPlacement;             // Override at md breakpoint
}
```

### Sizing rule of thumb

- Always set `minHeight` (or `height`) when using `direction: 'column'`. Without it, panels collapse on small screens.
- When using `direction: 'row'`, set `width` (often `'50%'`, `'33%'`) on each item.
- Use `ySizing: 'fill'` to make a panel grow to fill remaining vertical space.

### Responsive — `md` overrides

The default behavior on screens < md (Grafana theme breakpoint):

- `row` direction switches to `column`.
- Outer `maxWidth/maxHeight/width/height` constraints are removed.
- `SceneFlexLayout`'s `minHeight`/`height` is inherited by children (so column children stay sized).

Override per-element:

```ts
new SceneFlexLayout({
  direction: 'row',
  minHeight: 200,
  md: {
    direction: 'row',         // Force row even on small screens
    minHeight: 100,
  },
  children: [...],
});
```

## SceneCSSGridLayout

CSS Grid. Best for "auto-fit" responsive grids.

```ts
new SceneCSSGridLayout({
  templateColumns: "repeat(auto-fit, minmax(400px, 1fr))",
  autoRows: "320px",
  rowGap: 1, // Multiplied by Grafana's 8px design unit
  columnGap: 1,
  children: [
    new SceneCSSGridItem({ body: panel1 }),
    new SceneCSSGridItem({ body: panel2 }),
    new SceneCSSGridItem({ body: panel3 }),
    // ... grid auto-flows them
  ],
});
```

Properties:

```ts
{
  templateColumns: string;      // e.g. 'repeat(3, 1fr)' or 'repeat(auto-fit, minmax(400px, 1fr))'
  templateRows?: string;
  autoRows?: string;            // Default '320px'
  rowGap: number;
  columnGap: number;
  justifyItems?: CSSProperties['justifyItems'];
  alignItems?: CSSProperties['alignItems'];
  justifyContent?: CSSProperties['justifyContent'];
  md?: SceneCSSGridLayoutState;
}
```

`SceneCSSGridItem` is optional — children of `SceneCSSGridLayout` can also be raw `VizPanel` or other scene objects.

### Pattern: dynamic grid driven by data

```ts
const grid = new SceneCSSGridLayout({
  templateColumns: "repeat(auto-fit, minmax(400px, 1fr))",
  children: [],
});

queryRunner.addActivationHandler(() => {
  const sub = queryRunner.subscribeToState(({ data }) => {
    if (data?.state !== LoadingState.Done) return;
    grid.setState({
      children: data.series.map((s) =>
        PanelBuilders.timeseries()
          .setTitle(s.name ?? "")
          .setData(new SceneDataNode({ data: { ...data, series: [s] } }))
          .build()
      ),
    });
  });
  return () => sub.unsubscribe();
});
```

## SceneGridLayout — draggable dashboard grid

Use this when end users should rearrange panels. Same engine that powers Grafana dashboards (`react-grid-layout`).

```ts
new SceneGridLayout({
  isDraggable: true,
  isResizable: true,
  isLazy: true, // Don't init off-screen panels
  UNSAFE_fitPanels: false,
  children: [
    new SceneGridItem({
      x: 0,
      y: 0,
      width: 12,
      height: 8,
      body: panelA,
    }),
    new SceneGridItem({
      x: 12,
      y: 0,
      width: 12,
      height: 8,
      body: panelB,
    }),
    new SceneGridRow({
      x: 0,
      y: 8,
      title: "Details",
      children: [
        new SceneGridItem({
          x: 0,
          y: 0,
          width: 24,
          height: 6,
          body: panelC,
        }),
      ],
    }),
  ],
});
```

24-column grid; `width`/`height` are in column/row units. Rows nest items with relative coordinates.

Don't use `SceneGridLayout` for static apps — `SceneFlexLayout` or `SceneCSSGridLayout` are simpler and more responsive.

## SplitLayout

Two panes with a resizable divider.

```ts
import { SplitLayout } from "@grafana/scenes";

new SplitLayout({
  direction: "row", // 'row' or 'column'
  primary: PanelBuilders.timeseries().setTitle("Left").build(),
  secondary: PanelBuilders.table().setTitle("Right").build(),
  initialSize: 0.6, // 60/40 split
  primaryPaneStyles: { minWidth: 300 },
  secondaryPaneStyles: { minWidth: 200 },
});
```

## Hiding and showing items

Set `isHidden: true` on a flex item to skip rendering. Combine with `ActWhenVariableChanged` for variable-controlled visibility:

```ts
const detailsItem = new SceneFlexItem({ body: detailsPanel, isHidden: true });

const behavior = new behaviors.ActWhenVariableChanged({
  variableName: "showDetails",
  onChange: (variable) => {
    detailsItem.setState({ isHidden: variable.getValue() !== "true" });
  },
});
```

## Repeating panels by variable

```ts
import { SceneByVariableRepeater, VariableValueOption } from "@grafana/scenes";

new SceneByVariableRepeater({
  variableName: "cluster",
  body: new SceneCSSGridLayout({ templateColumns: "1fr", children: [] }),
  getLayoutChild: (option: VariableValueOption) =>
    new SceneCSSGridItem({
      body: PanelBuilders.timeseries()
        .setTitle(option.label)
        .setData(
          new SceneQueryRunner({
            datasource: { type: "prometheus", uid: "prom" },
            queries: [{ refId: "A", expr: `up{cluster="${option.value}"}` }],
          }),
        )
        .build(),
    }),
});
```

## Repeating by data series

`SceneByFrameRepeater` — one panel per data frame:

```ts
new SceneByFrameRepeater({
  body: new SceneCSSGridLayout({ children: [] }),
  getLayoutChild: (data, frame, frameIndex) =>
    new SceneCSSGridItem({
      body: PanelBuilders.timeseries().setTitle(frame.name).build(),
    }),
});
```

## Common patterns

### Header + main + footer

```ts
new SceneFlexLayout({
  direction: "column",
  children: [
    new SceneFlexItem({ height: 80, body: headerObj }),
    new SceneFlexItem({ ySizing: "fill", body: mainBody }),
    new SceneFlexItem({ height: 40, body: footerObj }),
  ],
});
```

### Sidebar + content

```ts
new SceneFlexLayout({
  direction: "row",
  children: [
    new SceneFlexItem({ width: 240, body: sidebarObj }),
    new SceneFlexItem({ xSizing: "fill", body: contentObj }),
  ],
});
```

### KPI row + chart

```ts
new SceneFlexLayout({
  direction: "column",
  children: [
    new SceneFlexItem({
      height: 120,
      body: new SceneFlexLayout({
        direction: "row",
        children: [
          new SceneFlexItem({
            body: PanelBuilders.stat().setTitle("Total").build(),
          }),
          new SceneFlexItem({
            body: PanelBuilders.stat().setTitle("Errors").build(),
          }),
          new SceneFlexItem({
            body: PanelBuilders.stat().setTitle("p99").build(),
          }),
        ],
      }),
    }),
    new SceneFlexItem({
      ySizing: "fill",
      minHeight: 300,
      body: PanelBuilders.timeseries().setTitle("Trend").build(),
    }),
  ],
});
```
