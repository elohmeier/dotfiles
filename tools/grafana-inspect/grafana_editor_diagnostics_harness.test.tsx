import { act, render, waitFor, within } from "@testing-library/react";
import { DragDropContext, Droppable } from "@hello-pangea/dnd";

import {
  dataFrameFromJSON,
  type DataFrame,
  type DataFrameJSON,
  type DataTransformerConfig,
  LoadingState,
  preProcessPanelData,
  standardTransformersRegistry,
} from "@grafana/data";
import { getStandardTransformers } from "app/features/transformers/standardTransformers";
import { TransformationOperationRows } from "app/features/dashboard/components/TransformationsEditor/TransformationOperationRows";
import { initTemplateSrv } from "test/helpers/initTemplateSrv";

import fs from "node:fs";

interface HarnessPanel {
  id: string;
  title: string;
  targets: Array<Record<string, unknown>>;
  transformations: DataTransformerConfig[];
  frames: DataFrameJSON[];
}

interface HarnessInput {
  schemaVersion: 1;
  dashboard: string;
  variables?: Array<Record<string, unknown>>;
  panels: HarnessPanel[];
}

interface EditorAlert {
  transformationIndex: number;
  transformationId: string;
  transformationName: string;
  message: string;
}

interface PanelDiagnostics {
  id: string;
  title: string;
  alerts: EditorAlert[];
  unknownTransformations: Array<{ index: number; id: string }>;
}

interface HarnessOutput {
  schemaVersion: 1;
  grafanaVersion: string;
  dashboard: string;
  panels: PanelDiagnostics[];
}

function requiredEnvironment(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

function readInput(filename: string): HarnessInput {
  const value = JSON.parse(fs.readFileSync(filename, "utf8")) as HarnessInput;
  if (value.schemaVersion !== 1 || !Array.isArray(value.panels)) {
    throw new Error("unsupported editor diagnostics input");
  }
  return value;
}

function panelFrames(panel: HarnessPanel): DataFrame[] {
  return panel.frames.map((frame) => dataFrameFromJSON(frame));
}

function textContent(element: HTMLElement): string {
  return (element.textContent ?? "").replace(/\s+/g, " ").trim();
}

function waitForDomToSettle(element: HTMLElement): Promise<void> {
  return new Promise((resolve, reject) => {
    let quietTimer: ReturnType<typeof setTimeout>;
    const timeout = setTimeout(() => {
      observer.disconnect();
      reject(new Error("transformation editors did not settle"));
    }, 5_000);
    const finish = () => {
      clearTimeout(timeout);
      observer.disconnect();
      resolve();
    };
    const waitForQuietPeriod = () => {
      clearTimeout(quietTimer);
      quietTimer = setTimeout(finish, 50);
    };
    const observer = new MutationObserver(waitForQuietPeriod);
    observer.observe(element, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    waitForQuietPeriod();
  });
}

describe("Grafana editor diagnostics harness", () => {
  test("renders configured transformation editors and exports their alerts", async () => {
    const input = readInput(
      requiredEnvironment("GRAFANA_EDITOR_DIAGNOSTICS_INPUT"),
    );
    const outputPath = requiredEnvironment("GRAFANA_EDITOR_DIAGNOSTICS_OUTPUT");
    const grafanaPackage = JSON.parse(
      fs.readFileSync("package.json", "utf8"),
    ) as { version?: string };

    standardTransformersRegistry.setInit(getStandardTransformers);
    initTemplateSrv("grafana-editor-diagnostics", input.variables ?? []);

    const panels: PanelDiagnostics[] = [];
    for (const panel of input.panels) {
      const knownTransformations = panel.transformations.flatMap(
        (transformation, index) => {
          const registryItem = standardTransformersRegistry.getIfExists(
            transformation.id,
          );
          return registryItem ? [{ index, transformation, registryItem }] : [];
        },
      );
      const unknownTransformations = panel.transformations.flatMap(
        (transformation, index) =>
          standardTransformersRegistry.getIfExists(transformation.id)
            ? []
            : [{ index, id: transformation.id }],
      );
      const series = panelFrames(panel);
      const data = preProcessPanelData({
        state: LoadingState.Done,
        series,
        annotations: [],
        request: { targets: panel.targets } as never,
      });
      const configs = panel.transformations.map((transformation, index) => ({
        id: `${index} - ${transformation.id}`,
        transformation,
      }));
      const view = render(
        <DragDropContext onDragEnd={() => {}}>
          <Droppable droppableId="transformations-list" direction="vertical">
            {(provided) => (
              <div ref={provided.innerRef} {...provided.droppableProps}>
                <TransformationOperationRows
                  data={data}
                  configs={configs}
                  onChange={() => {}}
                  onRemove={() => {}}
                />
                {provided.placeholder}
              </div>
            )}
          </Droppable>
        </DragDropContext>,
      );

      await waitFor(() => {
        const editors = view.container.querySelectorAll(
          '[data-testid*="Transformation editor "]',
        );
        expect(editors).toHaveLength(knownTransformations.length);
      });
      await act(async () => {
        await waitForDomToSettle(view.container);
      });

      const editorElements = Array.from(
        view.container.querySelectorAll<HTMLElement>(
          '[data-testid*="Transformation editor "]',
        ),
      );
      const alerts = knownTransformations.flatMap(
        ({ index, transformation, registryItem }, knownIndex) =>
          within(editorElements[knownIndex])
            .queryAllByRole("alert")
            .map((alert) => ({
              transformationIndex: index,
              transformationId: transformation.id,
              transformationName: registryItem.name,
              message: textContent(alert),
            })),
      );

      panels.push({
        id: panel.id,
        title: panel.title,
        alerts,
        unknownTransformations,
      });
      view.unmount();
    }

    const output: HarnessOutput = {
      schemaVersion: 1,
      grafanaVersion: grafanaPackage.version ?? "unknown",
      dashboard: input.dashboard,
      panels,
    };
    fs.writeFileSync(
      outputPath,
      `${JSON.stringify(output, null, 2)}\n`,
      "utf8",
    );
  });
});
