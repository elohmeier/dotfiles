import { SceneAppPage } from "@grafana/scenes";
import { ROUTES } from "../../constants";
import { prefixRoute } from "../../utils/utils.routing";
import { helloWorldScene } from "./helloWorldScene";

export const helloWorldPage = new SceneAppPage({
  title: "Hello world",
  subTitle: "A minimal scene with a single text panel.",
  url: prefixRoute(ROUTES.HelloWorld),
  routePath: ROUTES.HelloWorld,
  getScene: () => helloWorldScene(),
});
