package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"sort"
	"strings"

	dashv2 "github.com/grafana/grafana/apps/dashboard/pkg/apis/dashboard/v2"
)

const jsonnetBaselineExtVar = "grafanaDashboardV2"

type stringList []string

func (values *stringList) String() string {
	return strings.Join(*values, ",")
}

func (values *stringList) Set(value string) error {
	*values = append(*values, value)
	return nil
}

func runRender(args []string) error {
	fs := newFlagSet("render")
	opts := conversionOptions{}
	jsonnetSource := fs.String("jsonnet", "", "Jsonnet source that reads std.extVar(\"grafanaDashboardV2\")")
	var jpaths stringList
	fs.Var(&jpaths, "jpath", "Jsonnet import path; repeat as needed")
	fs.StringVar(&opts.inputPath, "input", "", "baseline input JSON file, or - for stdin")
	fs.StringVar(&opts.inputFormat, "input-format", "", "required: classic, export, or v1")
	fs.StringVar(&opts.contextPath, "context", "", "complete conversion-context JSON from export-context")
	fs.StringVar(&opts.name, "name", "", "resource name (required for classic and export inputs)")
	fs.StringVar(&opts.namespace, "namespace", "", "resource namespace for classic and export inputs")
	fs.StringVar(&opts.outputPath, "output", "-", "output JSON file, or - for stdout")
	fs.StringVar(&opts.outputFormat, "output-format", outputSpec, "spec or resource")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() != 0 {
		return errors.New("render accepts options only")
	}
	if *jsonnetSource == "" {
		return errors.New("--jsonnet is required")
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
	if _, err := exec.LookPath("jsonnet"); err != nil {
		return errors.New("jsonnet executable not found in PATH")
	}

	catalog, err := loadConversionContext(opts.contextPath)
	if err != nil {
		return err
	}
	data, err := readBytes(opts.inputPath)
	if err != nil {
		return err
	}
	baseline, _, err := convertDashboard(data, opts, catalog)
	if err != nil {
		return err
	}

	temp, err := os.CreateTemp("", "grafana-dashboard-v2-*.json")
	if err != nil {
		return fmt.Errorf("create temporary v2 baseline: %w", err)
	}
	tempPath := temp.Name()
	defer os.Remove(tempPath)
	encoded, err := json.Marshal(baseline.Spec)
	if err != nil {
		temp.Close()
		return fmt.Errorf("encode temporary v2 baseline: %w", err)
	}
	if _, err := temp.Write(encoded); err != nil {
		temp.Close()
		return fmt.Errorf("write temporary v2 baseline: %w", err)
	}
	if err := temp.Close(); err != nil {
		return fmt.Errorf("close temporary v2 baseline: %w", err)
	}

	cmdArgs := []string{"--ext-code-file", jsonnetBaselineExtVar + "=" + tempPath}
	for _, path := range jpaths {
		cmdArgs = append(cmdArgs, "-J", path)
	}
	cmdArgs = append(cmdArgs, filepath.Clean(*jsonnetSource))
	cmd := exec.Command("jsonnet", cmdArgs...)
	result, err := cmd.Output()
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			return fmt.Errorf("Jsonnet render failed: %s", strings.TrimSpace(string(exitErr.Stderr)))
		}
		return fmt.Errorf("run jsonnet: %w", err)
	}
	rendered, err := decodeV2(result, outputSpec)
	if err != nil {
		return fmt.Errorf("Jsonnet output is not a stable v2 spec: %w", err)
	}
	if errs := dashv2.ValidateDashboardSpec(rendered); len(errs) > 0 {
		return fmt.Errorf("Jsonnet produced an invalid stable v2 spec: %s", joinFieldErrors(errs))
	}
	if err := auditV2Integrity(rendered); err != nil {
		return err
	}

	var output any = rendered.Spec
	if opts.outputFormat == outputResource {
		baseline.Spec = rendered.Spec
		output = baseline
	}
	if err := writeJSON(opts.outputPath, output); err != nil {
		return err
	}
	fmt.Fprintf(os.Stderr, "render validation passed: %d elements\n", len(rendered.Spec.Elements))
	return nil
}

func auditV2Integrity(dashboard *dashv2.Dashboard) error {
	refs, err := layoutElementReferences(dashboard.Spec.Layout)
	if err != nil {
		return fmt.Errorf("inspect rendered layout: %w", err)
	}
	elements := make([]string, 0, len(dashboard.Spec.Elements))
	for name := range dashboard.Spec.Elements {
		elements = append(elements, name)
	}
	sort.Strings(elements)
	sort.Strings(refs)
	if !slices.Equal(elements, refs) {
		return fmt.Errorf("rendered v2 integrity audit failed: layout references %v do not match elements %v", refs, elements)
	}
	return nil
}
