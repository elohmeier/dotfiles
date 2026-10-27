import { useQueryRunner, VizGridLayout, VizPanel } from "@grafana/scenes-react";
import React from "react";
import { DATASOURCE_REF } from "../../../constants";

export function HomePage() {
  const data = useQueryRunner({
    queries: [
      {
        refId: "A",
        expr: "rate(http_requests_total{env=\"$env\"}[5m])",
        legendFormat: "{{job}}",
      },
    ],
    datasource: DATASOURCE_REF,
    maxDataPoints: 1000,
  });

  return (
    <VizGridLayout>
      <VizPanel
        title="Request rate"
        viz="timeseries"
        dataProvider={data}
        options={{ legend: { displayMode: "list", placement: "right" } }}
        fieldConfig={{ defaults: { unit: "reqps" }, overrides: [] }}
      />
    </VizGridLayout>
  );
}
