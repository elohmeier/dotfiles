package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	dashv2 "github.com/grafana/grafana/apps/dashboard/pkg/apis/dashboard/v2"
	"k8s.io/apimachinery/pkg/util/validation/field"
)

func runValidate(args []string) error {
	fs := newFlagSet("validate")
	input := fs.String("input", "", "input JSON file, or - for stdin")
	inputFormat := fs.String("input-format", "resource", "resource or spec")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() != 0 {
		return errors.New("validate accepts options only")
	}
	data, err := readBytes(*input)
	if err != nil {
		return err
	}
	dashboard, err := decodeV2(data, *inputFormat)
	if err != nil {
		return err
	}
	if errs := dashv2.ValidateDashboardSpec(dashboard); len(errs) > 0 {
		return fmt.Errorf("Grafana v2 validation failed: %s", joinFieldErrors(errs))
	}
	if err := auditV2Integrity(dashboard); err != nil {
		return err
	}
	fmt.Printf("%s: valid dashboard.grafana.app/v2 %s\n", displayPath(*input), *inputFormat)
	return nil
}

func decodeV2(data []byte, inputFormat string) (*dashv2.Dashboard, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	dashboard := &dashv2.Dashboard{}
	switch inputFormat {
	case "resource":
		if err := decoder.Decode(dashboard); err != nil {
			return nil, fmt.Errorf("strictly decode v2 resource: %w", err)
		}
		if dashboard.APIVersion != dashv2.APIVERSION {
			return nil, fmt.Errorf("apiVersion must be %q, got %q", dashv2.APIVERSION, dashboard.APIVersion)
		}
		if dashboard.Kind != "Dashboard" {
			return nil, fmt.Errorf("kind must be Dashboard, got %q", dashboard.Kind)
		}
	case "spec":
		if err := decoder.Decode(&dashboard.Spec); err != nil {
			return nil, fmt.Errorf("strictly decode v2 spec: %w", err)
		}
		dashboard.APIVersion = dashv2.APIVERSION
		dashboard.Kind = "Dashboard"
	default:
		return nil, errors.New("--input-format must be resource or spec")
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return nil, errors.New("input contains more than one JSON value")
		}
		return nil, fmt.Errorf("decode trailing JSON: %w", err)
	}
	return dashboard, nil
}

func joinFieldErrors(errs field.ErrorList) string {
	parts := make([]string, 0, len(errs))
	for _, err := range errs {
		parts = append(parts, err.Error())
	}
	return strings.Join(parts, "; ")
}

func runValidateLive(args []string) error {
	fs := newFlagSet("validate-live")
	input := fs.String("input", "", "v2 resource JSON file, or - for stdin")
	baseURL := fs.String("url", "", "Grafana base URL (or set GRAFANA_URL)")
	namespace := fs.String("namespace", "", "Grafana namespace used by the resource API")
	tokenEnv := fs.String("token-env", "GRAFANA_TOKEN", "environment variable containing a service-account token")
	caFile := fs.String("ca-file", "", "PEM CA bundle for the Grafana server")
	insecureTLS := fs.Bool("insecure-skip-tls-verify", false, "disable TLS certificate verification")
	hostHeader := fs.String("host-header", "", "override the HTTP Host header")
	var resolveRules stringList
	fs.Var(&resolveRules, "resolve", "connect host:port to address using curl --resolve syntax; repeat as needed")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() != 0 {
		return errors.New("validate-live accepts options only")
	}
	if *namespace == "" {
		return errors.New("--namespace is required")
	}
	data, err := readBytes(*input)
	if err != nil {
		return err
	}
	dashboard, err := decodeV2(data, "resource")
	if err != nil {
		return err
	}
	if dashboard.Namespace != "" && dashboard.Namespace != *namespace {
		return fmt.Errorf("resource metadata.namespace %q does not match --namespace %q", dashboard.Namespace, *namespace)
	}
	if errs := dashv2.ValidateDashboardSpec(dashboard); len(errs) > 0 {
		return fmt.Errorf("local Grafana v2 validation failed before live request: %s", joinFieldErrors(errs))
	}
	if err := auditV2Integrity(dashboard); err != nil {
		return err
	}

	client, base, err := newHTTPClient(httpOptions{
		baseURL: *baseURL, tokenEnv: *tokenEnv, caFile: *caFile, insecureTLS: *insecureTLS,
		timeout: 60 * time.Second, hostHeader: *hostHeader, resolveRules: resolveRules,
	})
	if err != nil {
		return err
	}
	endpoint := fmt.Sprintf(
		"%s/apis/dashboard.grafana.app/v2/namespaces/%s/dashboards?dryRun=All&fieldValidation=Strict",
		base,
		url.PathEscape(*namespace),
	)
	if err := doJSON(client, http.MethodPost, endpoint, *tokenEnv, bytes.NewReader(data), nil); err != nil {
		return fmt.Errorf("strict Grafana dry-run validation failed: %w", err)
	}
	fmt.Printf("%s: accepted by strict dashboard.grafana.app/v2 dry-run\n", displayPath(*input))
	return nil
}
