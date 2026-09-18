package main

import "testing"

func TestCheckPromQL(t *testing.T) {
	records := []promQLRecord{
		{Expr: `rate(vector_component_discarded_events_total{pod=~"metrics-forwarder.*"}[5m])`},
		{Expr: `up{host=~"\.\*"}`},
		{Expr: `up{host=~"\\.\\*"}`},
		{Expr: `sum(rate(up[5m])) +`},
	}
	if n := checkPromQL(records); n != 2 {
		t.Fatalf("got %d failures: %+v", n, records)
	}
	if records[0].Error != "" || records[1].Error == "" || records[2].Error != "" || records[3].Error == "" {
		t.Fatalf("unexpected results: %+v", records)
	}
}
