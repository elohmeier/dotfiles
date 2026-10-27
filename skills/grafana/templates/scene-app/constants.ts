import pluginJson from "./plugin.json";

export const PLUGIN_BASE_URL = `/a/${pluginJson.id}`;

export enum ROUTES {
  Home = "home",
  HelloWorld = "hello-world",
  WithTabs = "page-with-tabs",
  WithDrilldown = "page-with-drilldown",
}

export const DATASOURCE_REF = {
  uid: "${DATASOURCE_UID}",
  type: "${DATASOURCE_TYPE}",
};
