import { EmbeddedScene, PanelBuilders, SceneFlexItem, SceneFlexLayout, SceneQueryRunner } from "@grafana/scenes";
import { DATASOURCE_REF, PLUGIN_BASE_URL, ROUTES } from "../../constants";

const roomsQuery = {
  refId: "Rooms",
  datasource: DATASOURCE_REF,
  scenarioId: "random_walk",
  seriesCount: 8,
  alias: "__house_locations",
  min: 10,
  max: 27,
};

export function withDrilldownScene() {
  return new EmbeddedScene({
    $data: new SceneQueryRunner({
      datasource: DATASOURCE_REF,
      queries: [roomsQuery],
      maxDataPoints: 100,
    }),
    body: new SceneFlexLayout({
      direction: "column",
      children: [
        new SceneFlexItem({
          height: 320,
          body: PanelBuilders.table()
            .setTitle("Rooms — click a name to drill down")
            // Add a data link from the room name to the drilldown route.
            .setOverrides((b) =>
              b
                .matchFieldsWithName("Field")
                .overrideLinks([
                  {
                    title: "Open ${__value.text}",
                    url:
                      `${PLUGIN_BASE_URL}/${ROUTES.WithDrilldown}/room/\${__value.text:percentencode}\${__url.params}`,
                  },
                ])
            )
            .build(),
        }),
        new SceneFlexItem({
          ySizing: "fill",
          minHeight: 200,
          body: PanelBuilders.timeseries().setTitle("All rooms — temperature").build(),
        }),
      ],
    }),
  });
}
