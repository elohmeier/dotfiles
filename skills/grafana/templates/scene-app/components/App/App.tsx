import { AppRootProps } from "@grafana/data";
import { config } from "@grafana/runtime";
import { SceneApp, useSceneApp } from "@grafana/scenes";
import { Alert } from "@grafana/ui";
import React from "react";
import { DATASOURCE_REF } from "../../constants";
import { helloWorldPage } from "../../pages/HelloWorld/helloWorldPage";
import { homePage } from "../../pages/Home/homePage";
import { withDrilldownPage } from "../../pages/WithDrilldown/withDrilldownPage";
import { withTabsPage } from "../../pages/WithTabs/withTabsPage";
import { PluginPropsContext } from "../../utils/utils.plugin";

function getSceneApp() {
  return new SceneApp({
    pages: [homePage, helloWorldPage, withTabsPage, withDrilldownPage],
    urlSyncOptions: {
      updateUrlOnInit: true,
      createBrowserHistorySteps: true,
    },
  });
}

function AppWithScenes() {
  // The module-scope factory gives useSceneApp a stable cache key. Do not replace it with an inline callback.
  const scene = useSceneApp(getSceneApp);

  return (
    <>
      {!config.datasources[DATASOURCE_REF.uid] && (
        <Alert title={`Missing ${DATASOURCE_REF.uid} datasource`}>
          This app needs the <b>{DATASOURCE_REF.type}</b> datasource at uid{" "}
          <code>{DATASOURCE_REF.uid}</code>. Provision one in <code>provisioning/datasources/default.yaml</code>{" "}
          or update <code>DATASOURCE_REF</code> in <code>constants.ts</code>.
        </Alert>
      )}
      <scene.Component model={scene} />
    </>
  );
}

export default function App(props: AppRootProps) {
  return (
    <PluginPropsContext.Provider value={props}>
      <AppWithScenes />
    </PluginPropsContext.Provider>
  );
}
