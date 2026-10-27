import { AppRootProps } from "@grafana/data";
import {
  CustomVariable,
  RefreshPicker,
  SceneContextProvider,
  TimeRangePicker,
  VariableControl,
} from "@grafana/scenes-react";
import { Stack } from "@grafana/ui";
import React from "react";
import { Route, Routes } from "react-router-dom";
import { PluginPropsContext } from "../../utils/utils.plugin";
import { DetailsPage } from "./pages/DetailsPage";
import { HomePage } from "./pages/HomePage";

function AppShell() {
  return (
    <SceneContextProvider timeRange={{ from: "now-1h", to: "now" }} withQueryController>
      <CustomVariable name="env" query="dev, test, prod" initialValue="dev">
        <Stack direction="row" gap={1} alignItems="center">
          <VariableControl name="env" />
          <div style={{ flexGrow: 1 }} />
          <TimeRangePicker />
          <RefreshPicker />
        </Stack>
        <Routes>
          <Route path="" element={<HomePage />} />
          <Route path="/details/:id" element={<DetailsPage />} />
        </Routes>
      </CustomVariable>
    </SceneContextProvider>
  );
}

export default function App(props: AppRootProps) {
  return (
    <PluginPropsContext.Provider value={props}>
      <AppShell />
    </PluginPropsContext.Provider>
  );
}
