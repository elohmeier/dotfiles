import { AppRootProps } from "@grafana/data";
import React, { useContext } from "react";

// Makes AppRootProps available anywhere in the app via context.
export const PluginPropsContext = React.createContext<AppRootProps | null>(null);

export const usePluginProps = () => {
  return useContext(PluginPropsContext);
};

export const usePluginMeta = () => {
  const props = usePluginProps();
  return props?.meta;
};
