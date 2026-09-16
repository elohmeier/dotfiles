package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/grafana/grafana/apps/dashboard/pkg/migration/schemaversion"
	common "github.com/grafana/grafana/pkg/apimachinery/apis/common/v0alpha1"
)

const conversionContextVersion = 1
const libraryElementPageSize = 100

type conversionContext struct {
	Version         int                   `json:"version"`
	Datasources     datasourceCatalog     `json:"datasources"`
	LibraryElements libraryElementCatalog `json:"libraryElements"`
}

type datasourceCatalog struct {
	Complete bool                `json:"complete"`
	Items    []contextDatasource `json:"items"`
}

type libraryElementCatalog struct {
	Complete bool                    `json:"complete"`
	Items    []contextLibraryElement `json:"items"`
}

type contextDatasource struct {
	UID        string `json:"uid"`
	Name       string `json:"name"`
	Type       string `json:"type"`
	ID         int64  `json:"id,omitempty"`
	Default    bool   `json:"default,omitempty"`
	APIVersion string `json:"apiVersion,omitempty"`
}

type apiDatasource struct {
	UID        string `json:"uid"`
	Name       string `json:"name"`
	Type       string `json:"type"`
	ID         int64  `json:"id"`
	IsDefault  bool   `json:"isDefault"`
	APIVersion string `json:"apiVersion"`
}

type contextLibraryElement struct {
	UID         string         `json:"uid"`
	Name        string         `json:"name"`
	Kind        int64          `json:"kind"`
	Type        string         `json:"type"`
	Description string         `json:"description,omitempty"`
	FolderUID   string         `json:"folderUid,omitempty"`
	Model       map[string]any `json:"model,omitempty"`
}

func loadConversionContext(path string) (*conversionContext, error) {
	if path == "" {
		return nil, errors.New("--context is required; use export-context to create a complete snapshot")
	}
	var cfg conversionContext
	if err := readJSON(path, &cfg); err != nil {
		return nil, err
	}
	if cfg.Version != conversionContextVersion {
		return nil, fmt.Errorf("%s: context version must be %d, got %d", path, conversionContextVersion, cfg.Version)
	}
	if !cfg.Datasources.Complete || !cfg.LibraryElements.Complete {
		return nil, fmt.Errorf("%s: datasources.complete and libraryElements.complete must both be true", path)
	}
	if err := cfg.validate(); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return &cfg, nil
}

func (c *conversionContext) validate() error {
	uidSeen := map[string]bool{}
	nameSeen := map[string]bool{}
	defaults := 0
	for i, ds := range c.Datasources.Items {
		if ds.UID == "" || ds.Name == "" || ds.Type == "" {
			return fmt.Errorf("datasources.items[%d] requires non-empty uid, name, and type", i)
		}
		if uidSeen[ds.UID] {
			return fmt.Errorf("duplicate datasource uid %q", ds.UID)
		}
		if nameSeen[ds.Name] {
			return fmt.Errorf("duplicate datasource name %q", ds.Name)
		}
		uidSeen[ds.UID] = true
		nameSeen[ds.Name] = true
		if ds.Default {
			defaults++
		}
	}
	if defaults > 1 {
		return fmt.Errorf("datasource catalog has %d defaults; at most one is valid", defaults)
	}

	librarySeen := map[string]bool{}
	for i, elem := range c.LibraryElements.Items {
		if elem.UID == "" || elem.Name == "" {
			return fmt.Errorf("libraryElements.items[%d] requires non-empty uid and name", i)
		}
		if librarySeen[elem.UID] {
			return fmt.Errorf("duplicate library element uid %q", elem.UID)
		}
		librarySeen[elem.UID] = true
	}
	return nil
}

type datasourceProvider struct {
	index *schemaversion.DatasourceIndex
}

func (p *datasourceProvider) Index(context.Context) *schemaversion.DatasourceIndex {
	return p.index
}

type libraryElementProvider struct {
	items []schemaversion.LibraryElementInfo
}

func (p *libraryElementProvider) GetLibraryElementInfo(context.Context) []schemaversion.LibraryElementInfo {
	return p.items
}

func (c *conversionContext) providers() (*datasourceProvider, *libraryElementProvider) {
	datasources := make([]schemaversion.DataSourceInfo, 0, len(c.Datasources.Items))
	for _, ds := range c.Datasources.Items {
		datasources = append(datasources, schemaversion.DataSourceInfo{
			Default: ds.Default, UID: ds.UID, Name: ds.Name, Type: ds.Type, ID: ds.ID, APIVersion: ds.APIVersion,
		})
	}
	libraryElements := make([]schemaversion.LibraryElementInfo, 0, len(c.LibraryElements.Items))
	for _, elem := range c.LibraryElements.Items {
		libraryElements = append(libraryElements, schemaversion.LibraryElementInfo{
			UID: elem.UID, Name: elem.Name, Kind: elem.Kind, Type: elem.Type,
			Description: elem.Description, FolderUID: elem.FolderUID,
			Model: common.Unstructured{Object: elem.Model},
		})
	}
	return &datasourceProvider{index: schemaversion.NewDatasourceIndex(datasources)}, &libraryElementProvider{items: libraryElements}
}

type httpOptions struct {
	baseURL      string
	tokenEnv     string
	caFile       string
	insecureTLS  bool
	timeout      time.Duration
	hostHeader   string
	resolveRules []string
}

func newHTTPClient(opts httpOptions) (*http.Client, string, error) {
	base := strings.TrimRight(opts.baseURL, "/")
	if base == "" {
		base = strings.TrimRight(os.Getenv("GRAFANA_URL"), "/")
	}
	parsed, err := url.Parse(base)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return nil, "", fmt.Errorf("--url or GRAFANA_URL must be an absolute HTTP(S) URL")
	}

	if opts.caFile == "" {
		opts.caFile = os.Getenv("GRAFANA_CA_FILE")
	}
	if opts.hostHeader == "" {
		opts.hostHeader = os.Getenv("GRAFANA_HOST_HEADER")
	}
	if len(opts.resolveRules) == 0 {
		opts.resolveRules = strings.FieldsFunc(os.Getenv("GRAFANA_RESOLVE"), func(r rune) bool { return r == ',' || r == ' ' })
	}
	if value := os.Getenv("GRAFANA_TLS_VERIFY"); value != "" {
		verify, err := strconv.ParseBool(value)
		if err != nil {
			return nil, "", fmt.Errorf("GRAFANA_TLS_VERIFY: %w", err)
		}
		opts.insecureTLS = opts.insecureTLS || !verify
	}
	tlsConfig := &tls.Config{MinVersion: tls.VersionTLS12, ServerName: os.Getenv("GRAFANA_SNI_HOSTNAME")}
	if opts.insecureTLS {
		tlsConfig.InsecureSkipVerify = true //nolint:gosec -- explicit CLI option
	}
	if opts.caFile != "" {
		pem, err := os.ReadFile(opts.caFile)
		if err != nil {
			return nil, "", fmt.Errorf("read CA file: %w", err)
		}
		pool, err := x509.SystemCertPool()
		if err != nil {
			return nil, "", fmt.Errorf("load system CA pool: %w", err)
		}
		if !pool.AppendCertsFromPEM(pem) {
			return nil, "", errors.New("CA file contains no parseable certificates")
		}
		tlsConfig.RootCAs = pool
	}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.TLSClientConfig = tlsConfig
	if len(opts.resolveRules) > 0 {
		rules, err := parseResolveRules(opts.resolveRules)
		if err != nil {
			return nil, "", err
		}
		dialer := &net.Dialer{Timeout: 30 * time.Second, KeepAlive: 30 * time.Second}
		transport.DialContext = func(ctx context.Context, network, address string) (net.Conn, error) {
			if replacement, ok := rules[address]; ok {
				address = replacement
			}
			return dialer.DialContext(ctx, network, address)
		}
	}
	var roundTripper http.RoundTripper = transport
	if opts.hostHeader != "" {
		roundTripper = hostHeaderTransport{base: transport, host: opts.hostHeader}
	}
	return &http.Client{Transport: roundTripper, Timeout: opts.timeout}, base, nil
}

type hostHeaderTransport struct {
	base http.RoundTripper
	host string
}

func (t hostHeaderTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	clone := req.Clone(req.Context())
	clone.Host = t.host
	return t.base.RoundTrip(clone)
}

func parseResolveRules(values []string) (map[string]string, error) {
	rules := make(map[string]string, len(values))
	for _, value := range values {
		parts := strings.SplitN(value, ":", 3)
		if len(parts) != 3 || parts[0] == "" || parts[1] == "" || parts[2] == "" {
			return nil, fmt.Errorf("--resolve must use curl syntax host:port:address, got %q", value)
		}
		address := strings.TrimPrefix(strings.TrimSuffix(parts[2], "]"), "[")
		rules[net.JoinHostPort(parts[0], parts[1])] = net.JoinHostPort(address, parts[1])
	}
	return rules, nil
}

func doJSON(client *http.Client, method, endpoint, tokenEnv string, body io.Reader, target any) error {
	req, err := http.NewRequest(method, endpoint, body)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "grafana-dashboard/1")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if tokenEnv != "" {
		if token := os.Getenv(tokenEnv); token != "" {
			req.Header.Set("Authorization", "Bearer "+token)
		}
	}
	if req.Header.Get("Authorization") == "" && os.Getenv("GRAFANA_USERNAME") != "" {
		req.SetBasicAuth(os.Getenv("GRAFANA_USERNAME"), os.Getenv("GRAFANA_PASSWORD"))
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	if err != nil {
		return err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		var status struct {
			Message string `json:"message"`
		}
		_ = json.Unmarshal(data, &status)
		if status.Message == "" {
			status.Message = strings.TrimSpace(string(data))
		}
		return fmt.Errorf("%s %s: HTTP %d: %s", method, endpoint, resp.StatusCode, status.Message)
	}
	if target != nil && len(data) > 0 {
		if err := json.Unmarshal(data, target); err != nil {
			return fmt.Errorf("decode response from %s: %w", endpoint, err)
		}
	}
	return nil
}

func runExportContext(args []string) error {
	fs := newFlagSet("export-context")
	baseURL := fs.String("url", "", "Grafana base URL (or set GRAFANA_URL)")
	output := fs.String("output", "-", "output JSON file, or - for stdout")
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
		return errors.New("export-context accepts options only")
	}

	client, base, err := newHTTPClient(httpOptions{
		baseURL: *baseURL, tokenEnv: *tokenEnv, caFile: *caFile, insecureTLS: *insecureTLS,
		timeout: 60 * time.Second, hostHeader: *hostHeader, resolveRules: resolveRules,
	})
	if err != nil {
		return err
	}
	ctx, err := fetchConversionContext(client, base, *tokenEnv)
	if err != nil {
		return err
	}
	return writeJSON(*output, ctx)
}

func fetchConversionContext(client *http.Client, base, tokenEnv string) (*conversionContext, error) {
	var apiList []apiDatasource
	if err := doJSON(client, http.MethodGet, base+"/api/datasources", tokenEnv, nil, &apiList); err != nil {
		return nil, fmt.Errorf("export datasources: %w", err)
	}
	list := make([]contextDatasource, 0, len(apiList))
	for _, summary := range apiList {
		var detail apiDatasource
		endpoint := base + "/api/datasources/uid/" + url.PathEscape(summary.UID)
		if err := doJSON(client, http.MethodGet, endpoint, tokenEnv, nil, &detail); err != nil {
			return nil, fmt.Errorf("export datasource %q: %w", summary.UID, err)
		}
		list = append(list, contextDatasource{
			UID: summary.UID, Name: summary.Name, Type: summary.Type, ID: summary.ID,
			Default: summary.IsDefault, APIVersion: detail.APIVersion,
		})
	}
	sort.Slice(list, func(i, j int) bool { return list[i].UID < list[j].UID })

	library := make([]contextLibraryElement, 0)
	for page := 1; page <= 100; page++ {
		var response struct {
			Result struct {
				Elements []contextLibraryElement `json:"elements"`
			} `json:"result"`
		}
		endpoint := fmt.Sprintf("%s/api/library-elements?perPage=%d&page=%d", base, libraryElementPageSize, page)
		if err := doJSON(client, http.MethodGet, endpoint, tokenEnv, nil, &response); err != nil {
			return nil, fmt.Errorf("export library elements page %d: %w", page, err)
		}
		library = append(library, response.Result.Elements...)
		if len(response.Result.Elements) < libraryElementPageSize {
			break
		}
		if page == 100 {
			return nil, errors.New("library element export exceeded the 100-page safety limit")
		}
	}
	sort.Slice(library, func(i, j int) bool { return library[i].UID < library[j].UID })

	result := &conversionContext{
		Version:         conversionContextVersion,
		Datasources:     datasourceCatalog{Complete: true, Items: list},
		LibraryElements: libraryElementCatalog{Complete: true, Items: library},
	}
	if err := result.validate(); err != nil {
		return nil, fmt.Errorf("Grafana returned an invalid conversion context: %w", err)
	}
	return result, nil
}
