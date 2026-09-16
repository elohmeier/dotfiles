package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"

	dashv1 "github.com/grafana/grafana/apps/dashboard/pkg/apis/dashboard/v1"
	dashv2 "github.com/grafana/grafana/apps/dashboard/pkg/apis/dashboard/v2"
	"github.com/grafana/grafana/apps/dashboard/pkg/migration"
	"github.com/grafana/grafana/apps/dashboard/pkg/migration/conversion"
	"github.com/grafana/grafana/apps/dashboard/pkg/migration/schemaversion"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

const (
	inputClassic = "classic"
	inputExport  = "export"
	inputV1      = "v1"

	outputResource = "resource"
	outputSpec     = "spec"
)

type conversionOptions struct {
	inputPath    string
	inputFormat  string
	contextPath  string
	name         string
	namespace    string
	outputPath   string
	outputFormat string
}

func runConvert(args []string) error {
	fs := newFlagSet("convert")
	opts := conversionOptions{}
	fs.StringVar(&opts.inputPath, "input", "", "input JSON file, or - for stdin")
	fs.StringVar(&opts.inputFormat, "input-format", "", "required: classic, export, or v1")
	fs.StringVar(&opts.contextPath, "context", "", "complete conversion-context JSON from export-context")
	fs.StringVar(&opts.name, "name", "", "resource name (required for classic and export inputs)")
	fs.StringVar(&opts.namespace, "namespace", "", "resource namespace for classic and export inputs")
	fs.StringVar(&opts.outputPath, "output", "-", "output JSON file, or - for stdout")
	fs.StringVar(&opts.outputFormat, "output-format", outputResource, "resource or spec")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() != 0 {
		return errors.New("convert accepts options only")
	}
	if opts.inputFormat != inputClassic && opts.inputFormat != inputExport && opts.inputFormat != inputV1 {
		return errors.New("--input-format must be classic, export, or v1")
	}
	if opts.outputFormat != outputResource && opts.outputFormat != outputSpec {
		return errors.New("--output-format must be resource or spec")
	}
	if (opts.inputFormat == inputClassic || opts.inputFormat == inputExport) && opts.name == "" {
		return errors.New("--name is required for classic and export inputs")
	}

	catalog, err := loadConversionContext(opts.contextPath)
	if err != nil {
		return err
	}
	data, err := readBytes(opts.inputPath)
	if err != nil {
		return err
	}
	out, audit, err := convertDashboard(data, opts, catalog)
	if err != nil {
		return err
	}

	var value any = out
	if opts.outputFormat == outputSpec {
		value = out.Spec
	}
	if err := writeJSON(opts.outputPath, value); err != nil {
		return err
	}
	fmt.Fprintf(
		os.Stderr,
		"conversion audit passed: %d panels, %d queries, %d transformations, %d annotations, %d variables\n",
		audit.Panels, audit.Queries, audit.Transformations, audit.Annotations, audit.Variables,
	)
	return nil
}

func convertDashboard(data []byte, opts conversionOptions, catalog *conversionContext) (*dashv2.Dashboard, auditStats, error) {
	dsProvider, libraryProvider := catalog.providers()
	if err := preflightContext(catalog); err != nil {
		return nil, auditStats{}, err
	}

	var source *dashv1.Dashboard
	switch opts.inputFormat {
	case inputClassic, inputExport:
		var payload map[string]any
		if err := json.Unmarshal(data, &payload); err != nil {
			return nil, auditStats{}, fmt.Errorf("decode %s as JSON: %w", displayPath(opts.inputPath), err)
		}
		dashboardJSON := payload
		if opts.inputFormat == inputExport {
			unwrapped, ok := payload["dashboard"].(map[string]any)
			if !ok {
				return nil, auditStats{}, errors.New("export input requires a top-level dashboard object")
			}
			dashboardJSON = unwrapped
		}
		migration.ResetForTesting()
		migration.Initialize(dsProvider, libraryProvider, time.Minute)
		if err := migration.Migrate(context.Background(), dashboardJSON, schemaversion.LATEST_VERSION); err != nil {
			return nil, auditStats{}, fmt.Errorf("Grafana schema migration failed: %w", err)
		}
		migration.EnsurePanelsHaveUniqueIds(dashboardJSON)
		source = &dashv1.Dashboard{
			TypeMeta:   metav1.TypeMeta{Kind: "Dashboard", APIVersion: dashv1.APIVERSION},
			ObjectMeta: metav1.ObjectMeta{Name: opts.name, Namespace: opts.namespace},
		}
		source.Spec.Object = dashboardJSON
	case inputV1:
		decoder := json.NewDecoder(bytes.NewReader(data))
		if err := decoder.Decode(&source); err != nil {
			return nil, auditStats{}, fmt.Errorf("decode %s as v1 Dashboard: %w", displayPath(opts.inputPath), err)
		}
		if source == nil {
			return nil, auditStats{}, errors.New("v1 input is null")
		}
		if source.Kind != "Dashboard" {
			return nil, auditStats{}, fmt.Errorf("v1 input kind must be Dashboard, got %q", source.Kind)
		}
		if source.APIVersion != dashv1.APIVERSION && source.APIVersion != "dashboard.grafana.app/v1beta1" {
			return nil, auditStats{}, fmt.Errorf("v1 input apiVersion must be dashboard.grafana.app/v1 or v1beta1, got %q", source.APIVersion)
		}
		if source.Spec.Object == nil {
			return nil, auditStats{}, errors.New("v1 input spec must be an object")
		}
		migration.EnsurePanelsHaveUniqueIds(sourceDashboardObject(source.Spec.Object))
	}

	sourceObject := sourceDashboardObject(source.Spec.Object)
	if err := validateConversionReferences(sourceObject, catalog); err != nil {
		return nil, auditStats{}, err
	}

	out := &dashv2.Dashboard{}
	if err := conversion.Convert_V1beta1_to_V2(source, out, nil, dsProvider, libraryProvider); err != nil {
		return nil, auditStats{}, fmt.Errorf("Grafana v1-to-v2 conversion failed: %w", err)
	}
	if errs := dashv2.ValidateDashboardSpec(out); len(errs) > 0 {
		return nil, auditStats{}, fmt.Errorf("Grafana produced an invalid v2 dashboard: %s", joinFieldErrors(errs))
	}
	audit, err := auditConversion(sourceObject, out)
	if err != nil {
		return nil, auditStats{}, err
	}
	return out, audit, nil
}

func sourceDashboardObject(spec map[string]any) map[string]any {
	if nested, ok := spec["dashboard"].(map[string]any); ok {
		return nested
	}
	return spec
}

func preflightContext(catalog *conversionContext) error {
	if catalog == nil {
		return errors.New("conversion context is nil")
	}
	return catalog.validate()
}

func validateConversionReferences(dashboard map[string]any, catalog *conversionContext) error {
	byUID := map[string]contextDatasource{}
	byName := map[string]contextDatasource{}
	var defaultDS *contextDatasource
	for i := range catalog.Datasources.Items {
		ds := catalog.Datasources.Items[i]
		byUID[ds.UID] = ds
		byName[ds.Name] = ds
		if ds.Default {
			copy := ds
			defaultDS = &copy
		}
	}
	libraryUIDs := map[string]bool{}
	for _, elem := range catalog.LibraryElements.Items {
		libraryUIDs[elem.UID] = true
	}

	var issues []string
	panels := flattenSourcePanels(dashboard)
	for _, panel := range panels {
		id := numberString(panel["id"])
		if library, ok := panel["libraryPanel"].(map[string]any); ok {
			uid, _ := library["uid"].(string)
			if uid == "" || !libraryUIDs[uid] {
				issues = append(issues, fmt.Sprintf("panel %s references library element %q absent from the complete context", id, uid))
			}
		}
		panelDS := panel["datasource"]
		targets, _ := panel["targets"].([]any)
		for targetIndex, rawTarget := range targets {
			target, ok := rawTarget.(map[string]any)
			if !ok {
				issues = append(issues, fmt.Sprintf("panel %s target %d is not an object", id, targetIndex))
				continue
			}
			ref := target["datasource"]
			if ref == nil {
				ref = panelDS
			}
			if err := validateDatasourceRef(ref, byUID, byName, defaultDS); err != nil {
				refID, _ := target["refId"].(string)
				issues = append(issues, fmt.Sprintf("panel %s query %q: %v", id, refID, err))
			}
		}
	}
	if templating, ok := dashboard["templating"].(map[string]any); ok {
		if variables, ok := templating["list"].([]any); ok {
			for i, raw := range variables {
				variable, _ := raw.(map[string]any)
				variableType, _ := variable["type"].(string)
				switch variableType {
				case "query", "adhoc", "groupby":
					if err := validateDatasourceRef(variable["datasource"], byUID, byName, defaultDS); err != nil {
						issues = append(issues, fmt.Sprintf("variable %d (%s): %v", i, variableType, err))
					}
				}
			}
		}
	}
	if len(issues) > 0 {
		return fmt.Errorf("conversion context cannot resolve every reference:\n  - %s", strings.Join(issues, "\n  - "))
	}
	return nil
}

func validateDatasourceRef(ref any, byUID, byName map[string]contextDatasource, defaultDS *contextDatasource) error {
	if ref == nil {
		if defaultDS == nil {
			return errors.New("datasource is omitted and the complete context has no default datasource")
		}
		return nil
	}
	switch value := ref.(type) {
	case string:
		if strings.HasPrefix(value, "$") {
			return nil
		}
		if value == "-- Grafana --" || value == "grafana" || value == "-- Mixed --" || value == "mixed" || value == "__expr__" {
			return nil
		}
		if _, ok := byUID[value]; ok {
			return nil
		}
		if _, ok := byName[value]; ok {
			return nil
		}
		return fmt.Errorf("legacy datasource %q is absent from the complete context", value)
	case map[string]any:
		typeName, _ := value["type"].(string)
		uid, _ := value["uid"].(string)
		if strings.HasPrefix(uid, "$") {
			return nil
		}
		if typeName != "" && (uid != "" || typeName == "datasource") {
			return nil
		}
		if uid != "" {
			if _, ok := byUID[uid]; ok {
				return nil
			}
			if _, ok := byName[uid]; ok {
				return nil
			}
			return fmt.Errorf("datasource uid/name %q has no type and is absent from the complete context", uid)
		}
		if defaultDS == nil {
			return errors.New("datasource reference has neither type nor uid and the complete context has no default")
		}
		return nil
	default:
		return fmt.Errorf("datasource reference has unsupported JSON type %T", ref)
	}
}
