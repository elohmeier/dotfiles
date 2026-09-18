package main

import (
	"fmt"

	"github.com/prometheus/prometheus/promql/parser"
)

type promQLRecord struct {
	PanelID string `json:"panelId"`
	Title   string `json:"title"`
	RefID   string `json:"refId"`
	Expr    string `json:"expr"`
	Error   string `json:"error,omitempty"`
}

func checkPromQL(records []promQLRecord) int {
	failed := 0
	for i := range records {
		if _, err := parser.NewParser(parser.Options{}).ParseExpr(records[i].Expr); err != nil {
			records[i].Error = err.Error()
			failed++
		}
	}
	return failed
}

func runValidatePromQL(args []string) error {
	fs := newFlagSet("validate-promql")
	input := fs.String("input", "-", "JSON array of panelId/title/refId/expr records; - for stdin")
	if err := fs.Parse(args); err != nil {
		return err
	}
	var records []promQLRecord
	if err := readJSON(*input, &records); err != nil {
		return err
	}
	failed := checkPromQL(records)
	if err := writeJSON("-", records); err != nil {
		return err
	}
	if failed > 0 {
		return fmt.Errorf("%d invalid PromQL queries", failed)
	}
	return nil
}
