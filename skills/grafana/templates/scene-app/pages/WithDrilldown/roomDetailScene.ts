import { EmbeddedScene, PanelBuilders, SceneFlexItem, SceneFlexLayout, SceneQueryRunner } from "@grafana/scenes";
import { DATASOURCE_REF } from "../../constants";

export function roomDetailScene(roomName: string) {
  return new EmbeddedScene({
    $data: new SceneQueryRunner({
      datasource: DATASOURCE_REF,
      queries: [
        {
          refId: "A",
          datasource: DATASOURCE_REF,
          scenarioId: "random_walk",
          alias: roomName,
          min: 10,
          max: 30,
        },
      ],
      maxDataPoints: 200,
    }),
    body: new SceneFlexLayout({
      direction: "row",
      children: [
        new SceneFlexItem({
          width: "50%",
          minHeight: 320,
          body: PanelBuilders.timeseries()
            .setTitle(`${roomName} — temperature`)
            .build(),
        }),
        new SceneFlexItem({
          width: "50%",
          minHeight: 320,
          body: PanelBuilders.stat()
            .setTitle("Current")
            .setUnit("celsius")
            .setOption("reduceOptions", { values: false, calcs: ["lastNotNull"], fields: "" })
            .build(),
        }),
      ],
    }),
  });
}
