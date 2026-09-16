package main

import (
	"encoding/json"
	"strings"
	"testing"

	dashv2 "github.com/grafana/grafana/apps/dashboard/pkg/apis/dashboard/v2"
)

func testContext() *conversionContext {
	return &conversionContext{
		Version: conversionContextVersion,
		Datasources: datasourceCatalog{Complete: true, Items: []contextDatasource{
			{UID: "prom-main", Name: "Prometheus", Type: "prometheus", Default: true, APIVersion: "v1"},
		}},
		LibraryElements: libraryElementCatalog{Complete: true, Items: []contextLibraryElement{}},
	}
}

func TestConvertClassicUsesGrafanaMigrationAndStableConversion(t *testing.T) {
	payload := map[string]any{
		"schemaVersion": 42,
		"title":         "Conversion test",
		"panels": []any{
			map[string]any{
				"id": 1, "type": "timeseries", "title": "Requests", "pluginVersion": "13.1.0",
				"gridPos":    map[string]any{"x": 0, "y": 0, "w": 12, "h": 8},
				"datasource": map[string]any{"type": "prometheus", "uid": "prom-main"},
				"targets": []any{map[string]any{
					"refId": "A", "expr": "sum(rate(http_requests_total[5m]))",
					"datasource": map[string]any{"type": "prometheus", "uid": "prom-main"},
				}},
				"transformations": []any{map[string]any{"id": "renameByRegex", "options": map[string]any{"regex": "(.*)"}}},
				"fieldConfig": map[string]any{"defaults": map[string]any{
					"thresholds": map[string]any{"mode": "absolute", "steps": []any{
						map[string]any{"color": "green", "value": nil},
						map[string]any{"color": "red", "value": 80},
					}},
				}},
			},
		},
		"annotations": map[string]any{"list": []any{}},
		"templating":  map[string]any{"list": []any{}},
	}
	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	out, stats, err := convertDashboard(data, conversionOptions{
		inputPath: "test.json", inputFormat: inputClassic, name: "conversion-test", outputFormat: outputResource,
	}, testContext())
	if err != nil {
		t.Fatal(err)
	}
	if out.APIVersion != "dashboard.grafana.app/v2" {
		t.Fatalf("unexpected apiVersion %q", out.APIVersion)
	}
	panel := out.Spec.Elements["panel-1"].PanelKind
	if panel == nil {
		t.Fatal("panel-1 is not a Panel element")
	}
	if panel.Spec.VizConfig.Version != "13.1.0" {
		t.Fatalf("pluginVersion not preserved: %q", panel.Spec.VizConfig.Version)
	}
	if len(panel.Spec.Data.Spec.Transformations) != 1 || panel.Spec.Data.Spec.Transformations[0].Group != "renameByRegex" {
		t.Fatalf("transformation shape not preserved: %#v", panel.Spec.Data.Spec.Transformations)
	}
	if stats.Panels != 1 || stats.Queries != 1 || stats.Transformations != 1 {
		t.Fatalf("unexpected audit stats: %#v", stats)
	}
}

func TestConversionRequiresResolvableDefault(t *testing.T) {
	catalog := testContext()
	catalog.Datasources.Items[0].Default = false
	dashboard := map[string]any{
		"panels": []any{map[string]any{
			"id": 1, "type": "timeseries", "targets": []any{map[string]any{"refId": "A"}},
		}},
	}
	err := validateConversionReferences(dashboard, catalog)
	if err == nil || !strings.Contains(err.Error(), "no default datasource") {
		t.Fatalf("expected missing-default error, got %v", err)
	}
}

func TestConversionAcceptsDatasourceVariableUID(t *testing.T) {
	catalog := testContext()
	catalog.Datasources.Items[0].Default = false
	dashboard := map[string]any{
		"panels": []any{map[string]any{
			"id": 1, "type": "timeseries", "targets": []any{map[string]any{
				"refId": "A", "datasource": map[string]any{"uid": "${datasource}"},
			}},
		}},
	}
	if err := validateConversionReferences(dashboard, catalog); err != nil {
		t.Fatalf("datasource variable should not require catalog resolution: %v", err)
	}
}

func TestConvertPreservesBuiltinAnnotationWithoutDatasource(t *testing.T) {
	payload := map[string]any{
		"schemaVersion": 42,
		"title":         "Built-in annotation test",
		"panels":        []any{},
		"annotations": map[string]any{"list": []any{map[string]any{
			"name": "Annotations & Alerts", "builtIn": 1, "type": "dashboard",
		}}},
		"templating": map[string]any{"list": []any{}},
	}
	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	out, stats, err := convertDashboard(data, conversionOptions{
		inputPath: "test.json", inputFormat: inputClassic, name: "annotation-test", outputFormat: outputResource,
	}, testContext())
	if err != nil {
		t.Fatal(err)
	}
	if stats.Annotations != 1 || len(out.Spec.Annotations) != 1 {
		t.Fatalf("built-in annotation not preserved: stats=%#v annotations=%#v", stats, out.Spec.Annotations)
	}
}

func TestConvertPreservesLibraryPanelReference(t *testing.T) {
	catalog := testContext()
	catalog.LibraryElements.Items = []contextLibraryElement{{
		UID: "library-panel", Name: "Shared requests", Kind: 1, Type: "timeseries",
		Model: map[string]any{
			"id": 7, "type": "timeseries", "title": "Shared requests", "pluginVersion": "13.1.0",
			"datasource": map[string]any{"type": "prometheus", "uid": "prom-main"},
			"targets": []any{map[string]any{
				"refId": "A", "expr": "sum(rate(http_requests_total[5m]))",
				"datasource": map[string]any{"type": "prometheus", "uid": "prom-main"},
			}},
		},
	}}
	payload := map[string]any{
		"schemaVersion": 42,
		"title":         "Library panel test",
		"panels": []any{map[string]any{
			"id": 7, "type": "timeseries", "title": "Shared requests",
			"gridPos":      map[string]any{"x": 0, "y": 0, "w": 12, "h": 8},
			"libraryPanel": map[string]any{"uid": "library-panel", "name": "Shared requests"},
		}},
		"annotations": map[string]any{"list": []any{}},
		"templating":  map[string]any{"list": []any{}},
	}
	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	out, stats, err := convertDashboard(data, conversionOptions{
		inputPath: "test.json", inputFormat: inputClassic, name: "library-test", outputFormat: outputResource,
	}, catalog)
	if err != nil {
		t.Fatal(err)
	}
	element := out.Spec.Elements["panel-7"].LibraryPanelKind
	if element == nil || element.Spec.LibraryPanel.Uid != "library-panel" {
		t.Fatalf("library panel reference not preserved: %#v", out.Spec.Elements["panel-7"])
	}
	if stats.Panels != 1 {
		t.Fatalf("unexpected audit stats: %#v", stats)
	}
}

func TestAuditRejectsDroppedElement(t *testing.T) {
	payload := map[string]any{
		"schemaVersion": 42, "title": "Audit test",
		"panels": []any{map[string]any{
			"id": 1, "type": "text", "title": "Text", "pluginVersion": "13.1.0",
			"gridPos": map[string]any{"x": 0, "y": 0, "w": 12, "h": 8}, "targets": []any{},
		}},
		"annotations": map[string]any{"list": []any{}},
		"templating":  map[string]any{"list": []any{}},
	}
	data, _ := json.Marshal(payload)
	out, _, err := convertDashboard(data, conversionOptions{
		inputPath: "test.json", inputFormat: inputClassic, name: "audit-test", outputFormat: outputResource,
	}, testContext())
	if err != nil {
		t.Fatal(err)
	}
	delete(out.Spec.Elements, "panel-1")
	if _, err := auditConversion(payload, out); err == nil || !strings.Contains(err.Error(), "preservation audit failed") {
		t.Fatalf("expected preservation failure, got %v", err)
	}
}

func TestIntegrityAuditRejectsUnreferencedElement(t *testing.T) {
	dashboard := &dashv2.Dashboard{}
	dashboard.Spec.Elements = map[string]dashv2.DashboardElement{"panel-1": {}}
	if err := auditV2Integrity(dashboard); err == nil || !strings.Contains(err.Error(), "do not match elements") {
		t.Fatalf("expected layout integrity failure, got %v", err)
	}
}
