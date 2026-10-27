import { SceneAppPage } from "@grafana/scenes";
import { ROUTES } from "../../constants";
import { prefixRoute } from "../../utils/utils.routing";
import { homeScene } from "./homeScene";

export const homePage = new SceneAppPage({
  title: "Home",
  subTitle: "A scene with a query runner, a variable, and a custom widget.",
  url: prefixRoute(ROUTES.Home),
  routePath: ROUTES.Home,
  getScene: () => homeScene(),
});
