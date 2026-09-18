package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime/debug"
)

func main() {
	if err := run(os.Args[1:]); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return
		}
		fmt.Fprintf(os.Stderr, "grafana-dashboard: %v\n", err)
		os.Exit(1)
	}
}

func run(args []string) error {
	if len(args) == 0 {
		return usageError()
	}

	switch args[0] {
	case "convert":
		return runConvert(args[1:])
	case "render":
		return runRender(args[1:])
	case "validate":
		return runValidate(args[1:])
	case "validate-promql":
		return runValidatePromQL(args[1:])
	case "schema":
		return writeOpenAPI()
	case "validate-live":
		return runValidateLive(args[1:])
	case "export-context":
		return runExportContext(args[1:])
	case "version":
		info, _ := debug.ReadBuildInfo()
		for _, dep := range info.Deps {
			if dep.Path == "github.com/grafana/grafana/apps/dashboard" {
				fmt.Printf("Grafana dashboard module %s\n", dep.Version)
			}
		}
		return nil
	case "help", "-h", "--help":
		printUsage(os.Stdout)
		return nil
	default:
		return fmt.Errorf("unknown command %q\n\n%s", args[0], usageText())
	}
}

func usageError() error {
	return errors.New(usageText())
}

func usageText() string {
	return `usage: grafana-dashboard <command> [options]

Commands:
  convert          Convert classic JSON or a v1 resource to stable v2
  render           Convert a baseline, then apply a Jsonnet patch to its stable-v2 spec
  validate         Validate with Grafana's pinned stable-v2 Go types and CUE validator
  validate-promql  Parse interpolated PromQL query records with the upstream parser
  schema           Export pinned upstream OpenAPI for editor validation
  validate-live    Validate a v2 resource through Grafana's strict dry-run API
  export-context   Export conversion context from a live Grafana instance
  version          Print the pinned Grafana dashboard module version

Run grafana-dashboard <command> -h for command-specific options.`
}

func printUsage(w io.Writer) {
	fmt.Fprintln(w, usageText())
}

func newFlagSet(name string) *flag.FlagSet {
	fs := flag.NewFlagSet(name, flag.ContinueOnError)
	fs.SetOutput(os.Stderr)
	return fs
}

func readBytes(path string) ([]byte, error) {
	if path == "" {
		return nil, errors.New("--input is required")
	}
	if path == "-" {
		data, err := io.ReadAll(os.Stdin)
		if err != nil {
			return nil, fmt.Errorf("read stdin: %w", err)
		}
		return data, nil
	}
	data, err := os.ReadFile(filepath.Clean(path))
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", path, err)
	}
	return data, nil
}

func readJSON(path string, target any) error {
	data, err := readBytes(path)
	if err != nil {
		return err
	}
	if err := json.Unmarshal(data, target); err != nil {
		return fmt.Errorf("decode %s as JSON: %w", displayPath(path), err)
	}
	return nil
}

func writeJSON(path string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return fmt.Errorf("encode JSON: %w", err)
	}
	data = append(data, '\n')
	if path == "" || path == "-" {
		_, err = os.Stdout.Write(data)
		return err
	}
	if err := os.WriteFile(filepath.Clean(path), data, 0o644); err != nil {
		return fmt.Errorf("write %s: %w", path, err)
	}
	return nil
}

func displayPath(path string) string {
	if path == "-" {
		return "stdin"
	}
	return path
}
