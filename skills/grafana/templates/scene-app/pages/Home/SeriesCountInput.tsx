import { SceneComponentProps, SceneObjectBase, SceneObjectState } from "@grafana/scenes";
import { Input } from "@grafana/ui";
import React from "react";

interface SeriesCountInputState extends SceneObjectState {
  count: number;
}

export class SeriesCountInput extends SceneObjectBase<SeriesCountInputState> {
  public static Component = SeriesCountInputRenderer;

  public onChange = (count: number) => {
    this.setState({ count });
  };
}

function SeriesCountInputRenderer({ model }: SceneComponentProps<SeriesCountInput>) {
  const { count } = model.useState();

  return (
    <Input
      prefix="Series"
      defaultValue={count}
      width={20}
      type="number"
      onBlur={(e) => model.onChange(parseInt(e.currentTarget.value, 10))}
    />
  );
}
