import pluginJson from "./plugin.json";

export const PLUGIN_BASE_URL = `/a/${pluginJson.id}`;

export enum ROUTES {
  Home = "home",
}

// Replace with the datasource your app uses, or remove if not needed.
export const DATASOURCE_REF = {
  uid: "${DATASOURCE_UID}",
  type: "${DATASOURCE_TYPE}",
};
