import { SceneAppPage, SceneTimePicker, SceneTimeRange } from "@grafana/scenes";
import { ROUTES } from "../../constants";
import { prefixRoute } from "../../utils/utils.routing";
import { roomDetailScene } from "./roomDetailScene";
import { withDrilldownScene } from "./withDrilldownScene";

export const withDrilldownPage = new SceneAppPage({
  $timeRange: new SceneTimeRange({ from: "now-6h", to: "now" }),
  title: "Page with drilldown",
  subTitle: "Click a room in the table to drill down.",
  controls: [new SceneTimePicker({ isOnCanvas: true })],
  url: prefixRoute(ROUTES.WithDrilldown),
  routePath: `${ROUTES.WithDrilldown}/*`,
  getScene: withDrilldownScene,
  drilldowns: [
    {
      routePath: "room/:roomName/*",
      getPage(routeMatch, parent) {
        // SceneRouteMatch params come from React Router's useParams and are already decoded.
        const roomName = routeMatch.params.roomName!;
        const encodedRoomName = encodeURIComponent(roomName);

        return new SceneAppPage({
          url: `${prefixRoute(ROUTES.WithDrilldown)}/room/${encodedRoomName}`,
          routePath: "room/:roomName/*",
          title: `${roomName} details`,
          subTitle: "Drill-down view for a single room.",
          // Dynamic pages are not static scene children; wire their breadcrumb parent explicitly.
          getParentPage: () => parent,
          getScene: () => roomDetailScene(roomName),
        });
      },
    },
  ],
});
