import { useQueryRunner, VizGridLayout, VizPanel } from "@grafana/scenes-react";
import React from "react";
import { useParams } from "react-router-dom";
import { DATASOURCE_REF } from "../../../constants";

export function DetailsPage() {
  const { id } = useParams<{ id: string }>();

  const data = useQueryRunner({
    queries: [
      {
        refId: "A",
        expr: `rate(http_requests_total{env="$env", job="${id}"}[5m])`,
      },
    ],
    datasource: DATASOURCE_REF,
  });

  return (
    <VizGridLayout>
      <VizPanel title={`${id} — request rate`} viz="timeseries" dataProvider={data} />
      <VizPanel
        title="Latest"
        viz="stat"
        dataProvider={data}
        options={{ reduceOptions: { values: false, calcs: ["lastNotNull"], fields: "" } }}
      />
    </VizGridLayout>
  );
}
