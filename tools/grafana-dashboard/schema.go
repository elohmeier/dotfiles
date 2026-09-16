package main

import (
	dashv2 "github.com/grafana/grafana/apps/dashboard/pkg/apis/dashboard/v2"
	common "github.com/grafana/grafana/pkg/apimachinery/apis/common/v0alpha1"
	"k8s.io/kube-openapi/pkg/validation/spec"
)

func writeOpenAPI() error {
	schemas := map[string]any{}
	ref := func(name string) spec.Ref {
		return spec.MustCreateRef("#/components/schemas/" + name)
	}
	definitions := common.GetOpenAPIDefinitions(ref)
	for name, definition := range dashv2.GetOpenAPIDefinitions(ref) {
		definitions[name] = definition
	}
	var include func(string)
	include = func(name string) {
		if _, exists := schemas[name]; exists {
			return
		}
		definition := definitions[name]
		schemas[name] = definition.Schema
		for _, dependency := range definition.Dependencies {
			include(dependency)
		}
	}
	include((dashv2.Dashboard{}).OpenAPIModelName())
	return writeJSON("-", map[string]any{"components": map[string]any{"schemas": schemas}})
}
