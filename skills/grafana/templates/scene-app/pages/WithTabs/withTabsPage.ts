import { SceneAppPage } from "@grafana/scenes";
import { ROUTES } from "../../constants";
import { prefixRoute } from "../../utils/utils.routing";
import { homeScene } from "../Home/homeScene";

const getTab1Scene = () => homeScene(false, "__server_names");
const getTab2Scene = () => homeScene(false, "__house_locations");

export const withTabsPage = new SceneAppPage({
  title: "Page with tabs",
  subTitle: "Tabs share this page header and breadcrumb item.",
  // The trailing /* matters: it lets React Router descend into tab routes.
  url: prefixRoute(ROUTES.WithTabs),
  routePath: `${ROUTES.WithTabs}/*`,
  tabs: [
    new SceneAppPage({
      title: "Server names",
      url: prefixRoute(ROUTES.WithTabs),
      // The first tab is registered as the default route at the parent URL.
      routePath: "",
      getScene: getTab1Scene,
    }),
    new SceneAppPage({
      title: "House locations",
      url: prefixRoute(`${ROUTES.WithTabs}/locations`),
      // Child route paths are relative and never start with a slash.
      routePath: "locations",
      getScene: getTab2Scene,
    }),
  ],
});
