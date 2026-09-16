package main

import (
	"os"
	"testing"

	dashv2 "github.com/grafana/grafana/apps/dashboard/pkg/apis/dashboard/v2"
)

func TestValidateTabbedResource(t *testing.T) {
	data, err := os.ReadFile("testdata/tabbed-dashboard-v2.json")
	if err != nil {
		t.Fatal(err)
	}
	dashboard, err := decodeV2(data, "resource")
	if err != nil {
		t.Fatal(err)
	}
	if errors := dashv2.ValidateDashboardSpec(dashboard); len(errors) != 0 {
		t.Fatal(errors)
	}
	if err := auditV2Integrity(dashboard); err != nil {
		t.Fatal(err)
	}
}
