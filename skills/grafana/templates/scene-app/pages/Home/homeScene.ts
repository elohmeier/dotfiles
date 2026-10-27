import {
  CustomVariable,
  EmbeddedScene,
  PanelBuilders,
  SceneControlsSpacer,
  SceneFlexItem,
  SceneFlexLayout,
  SceneQueryRunner,
  SceneRefreshPicker,
  SceneTimePicker,
  SceneTimeRange,
  SceneVariableSet,
  VariableValueSelectors,
} from "@grafana/scenes";
import { DATASOURCE_REF } from "../../constants";
import { SeriesCountInput } from "./SeriesCountInput";

export function homeScene(showVariable = true, defaultSeries = "__server_names") {
  const timeRange = new SceneTimeRange({ from: "now-6h", to: "now" });

  const seriesVariable = new CustomVariable({
    name: "seriesToShow",
    label: "Series to show",
    value: "__server_names",
    query: "Server names : __server_names, House locations : __house_locations",
  });

  const queryRunner = new SceneQueryRunner({
    datasource: DATASOURCE_REF,
    queries: [
      {
        refId: "A",
        datasource: DATASOURCE_REF,
        scenarioId: "random_walk",
        seriesCount: 5,
        alias: showVariable ? "${seriesToShow}" : defaultSeries,
        min: 30,
        max: 60,
      },
    ],
    maxDataPoints: 100,
  });

  const seriesCountInput = new SeriesCountInput({ count: 5 });

  // Wire up custom input to query runner state.
  queryRunner.addActivationHandler(() => {
    const sub = seriesCountInput.subscribeToState(({ count }) => {
      queryRunner.setState({
        queries: [{ ...queryRunner.state.queries[0], seriesCount: count }],
      });
      queryRunner.runQueries();
    });
    return () => sub.unsubscribe();
  });

  return new EmbeddedScene({
    $timeRange: timeRange,
    $variables: new SceneVariableSet({ variables: showVariable ? [seriesVariable] : [] }),
    $data: queryRunner,
    body: new SceneFlexLayout({
      direction: "column",
      children: [
        new SceneFlexItem({
          minHeight: 300,
          body: PanelBuilders.timeseries()
            .setTitle(showVariable ? "${seriesToShow}" : defaultSeries)
            .build(),
        }),
      ],
    }),
    controls: [
      new VariableValueSelectors({}),
      new SceneControlsSpacer(),
      seriesCountInput,
      new SceneTimePicker({ isOnCanvas: true }),
      new SceneRefreshPicker({ intervals: ["5s", "1m", "1h"], isOnCanvas: true }),
    ],
  });
}
