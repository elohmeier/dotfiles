import { AppPlugin, type AppRootProps } from "@grafana/data";
import { initPluginTranslations } from "@grafana/i18n";
import { loadResources } from "@grafana/scenes";
import { LoadingPlaceholder } from "@grafana/ui";
import pluginJson from "plugin.json";
import React, { lazy, Suspense } from "react";

await initPluginTranslations(pluginJson.id, [loadResources]);

const LazyApp = lazy(() => import("./components/App/App"));

const App = (props: AppRootProps) => (
  <Suspense fallback={<LoadingPlaceholder text="" />}>
    <LazyApp {...props} />
  </Suspense>
);

export const plugin = new AppPlugin<{}>().setRootPage(App);
