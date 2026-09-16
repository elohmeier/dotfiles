package main

import (
	"encoding/json"
	"fmt"
	"slices"
	"sort"
	"strconv"
	"strings"

	dashv2 "github.com/grafana/grafana/apps/dashboard/pkg/apis/dashboard/v2"
)

type auditStats struct {
	Panels          int `json:"panels"`
	Queries         int `json:"queries"`
	Transformations int `json:"transformations"`
	Annotations     int `json:"annotations"`
	DashboardLinks  int `json:"dashboardLinks"`
	PanelLinks      int `json:"panelLinks"`
	Variables       int `json:"variables"`
}

type sourcePanelAudit struct {
	ID                string
	RefIDs            []string
	TransformationIDs []string
	PluginType        string
	PluginVersion     string
	PanelLinks        int
	LibraryElementUID string
}

func auditConversion(source map[string]any, target *dashv2.Dashboard) (auditStats, error) {
	sourceStats, sourcePanels, err := collectSourceAudit(source)
	if err != nil {
		return auditStats{}, fmt.Errorf("conversion audit could not inspect source: %w", err)
	}
	targetStats, targetPanels := collectTargetAudit(target)

	var issues []string
	compareCount := func(label string, sourceCount, targetCount int) {
		if sourceCount != targetCount {
			issues = append(issues, fmt.Sprintf("%s changed from %d to %d", label, sourceCount, targetCount))
		}
	}
	compareCount("panel count", sourceStats.Panels, targetStats.Panels)
	compareCount("query count", sourceStats.Queries, targetStats.Queries)
	compareCount("transformation count", sourceStats.Transformations, targetStats.Transformations)
	compareCount("annotation count", sourceStats.Annotations, targetStats.Annotations)
	compareCount("dashboard-link count", sourceStats.DashboardLinks, targetStats.DashboardLinks)
	compareCount("panel-link count", sourceStats.PanelLinks, targetStats.PanelLinks)
	compareCount("variable count", sourceStats.Variables, targetStats.Variables)

	for id, src := range sourcePanels {
		dst, ok := targetPanels[id]
		if !ok {
			issues = append(issues, fmt.Sprintf("panel id %s is missing from v2 elements", id))
			continue
		}
		if src.LibraryElementUID != "" {
			if dst.LibraryElementUID != src.LibraryElementUID {
				issues = append(issues, fmt.Sprintf("panel %s library uid changed from %q to %q", id, src.LibraryElementUID, dst.LibraryElementUID))
			}
			continue
		}
		if !slices.Equal(src.RefIDs, dst.RefIDs) {
			issues = append(issues, fmt.Sprintf("panel %s query refIds changed from %v to %v", id, src.RefIDs, dst.RefIDs))
		}
		if !slices.Equal(src.TransformationIDs, dst.TransformationIDs) {
			issues = append(issues, fmt.Sprintf("panel %s transformation ids changed from %v to %v", id, src.TransformationIDs, dst.TransformationIDs))
		}
		if src.PluginType != dst.PluginType {
			issues = append(issues, fmt.Sprintf("panel %s plugin type changed from %q to %q", id, src.PluginType, dst.PluginType))
		}
		if src.PluginVersion != dst.PluginVersion {
			issues = append(issues, fmt.Sprintf("panel %s plugin version changed from %q to %q", id, src.PluginVersion, dst.PluginVersion))
		}
	}
	for id := range targetPanels {
		if _, ok := sourcePanels[id]; !ok {
			issues = append(issues, fmt.Sprintf("v2 contains unexpected panel id %s", id))
		}
	}

	refs, err := layoutElementReferences(target.Spec.Layout)
	if err != nil {
		issues = append(issues, fmt.Sprintf("could not inspect layout references: %v", err))
	} else {
		elementNames := make([]string, 0, len(target.Spec.Elements))
		for name := range target.Spec.Elements {
			elementNames = append(elementNames, name)
		}
		sort.Strings(elementNames)
		sort.Strings(refs)
		if !slices.Equal(elementNames, refs) {
			issues = append(issues, fmt.Sprintf("layout references %v do not match elements %v", refs, elementNames))
		}
	}

	if len(issues) > 0 {
		return auditStats{}, fmt.Errorf("conversion preservation audit failed:\n  - %s", strings.Join(issues, "\n  - "))
	}
	return targetStats, nil
}

func collectSourceAudit(source map[string]any) (auditStats, map[string]sourcePanelAudit, error) {
	panels := flattenSourcePanels(source)
	stats := auditStats{Panels: len(panels)}
	result := make(map[string]sourcePanelAudit, len(panels))
	for i, panel := range panels {
		id := numberString(panel["id"])
		if id == "" {
			return auditStats{}, nil, fmt.Errorf("panel at flattened index %d has no numeric id", i)
		}
		if _, exists := result[id]; exists {
			return auditStats{}, nil, fmt.Errorf("duplicate panel id %s after Grafana ID normalization", id)
		}
		entry := sourcePanelAudit{ID: id}
		entry.PluginType, _ = panel["type"].(string)
		entry.PluginVersion, _ = panel["pluginVersion"].(string)
		if links, ok := panel["links"].([]any); ok {
			entry.PanelLinks = len(links)
			stats.PanelLinks += len(links)
		}
		if targets, ok := panel["targets"].([]any); ok {
			stats.Queries += len(targets)
			for _, raw := range targets {
				target, _ := raw.(map[string]any)
				refID, _ := target["refId"].(string)
				entry.RefIDs = append(entry.RefIDs, refID)
			}
		}
		if transformations, ok := panel["transformations"].([]any); ok {
			stats.Transformations += len(transformations)
			for _, raw := range transformations {
				transformation, _ := raw.(map[string]any)
				id, _ := transformation["id"].(string)
				entry.TransformationIDs = append(entry.TransformationIDs, id)
			}
		}
		if library, ok := panel["libraryPanel"].(map[string]any); ok {
			entry.LibraryElementUID, _ = library["uid"].(string)
		}
		result[id] = entry
	}
	if annotations, ok := source["annotations"].(map[string]any); ok {
		if list, ok := annotations["list"].([]any); ok {
			stats.Annotations = len(list)
		}
	}
	if links, ok := source["links"].([]any); ok {
		stats.DashboardLinks = len(links)
	}
	if templating, ok := source["templating"].(map[string]any); ok {
		if variables, ok := templating["list"].([]any); ok {
			stats.Variables = len(variables)
		}
	}
	return stats, result, nil
}

func flattenSourcePanels(source map[string]any) []map[string]any {
	var result []map[string]any
	panels, _ := source["panels"].([]any)
	for _, raw := range panels {
		panel, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		panelType, _ := panel["type"].(string)
		if panelType == "row" {
			children, _ := panel["panels"].([]any)
			for _, rawChild := range children {
				if child, ok := rawChild.(map[string]any); ok {
					result = append(result, child)
				}
			}
			continue
		}
		result = append(result, panel)
	}
	return result
}

func collectTargetAudit(target *dashv2.Dashboard) (auditStats, map[string]sourcePanelAudit) {
	stats := auditStats{
		Panels:         len(target.Spec.Elements),
		Annotations:    len(target.Spec.Annotations),
		DashboardLinks: len(target.Spec.Links),
		Variables:      len(target.Spec.Variables),
	}
	panels := make(map[string]sourcePanelAudit, len(target.Spec.Elements))
	for _, element := range target.Spec.Elements {
		if element.PanelKind != nil {
			panel := element.PanelKind.Spec
			id := numberString(panel.Id)
			entry := sourcePanelAudit{
				ID: id, PluginType: panel.VizConfig.Group, PluginVersion: panel.VizConfig.Version,
				PanelLinks: len(panel.Links),
			}
			stats.PanelLinks += len(panel.Links)
			stats.Queries += len(panel.Data.Spec.Queries)
			for _, query := range panel.Data.Spec.Queries {
				entry.RefIDs = append(entry.RefIDs, query.Spec.RefId)
			}
			stats.Transformations += len(panel.Data.Spec.Transformations)
			for _, transformation := range panel.Data.Spec.Transformations {
				entry.TransformationIDs = append(entry.TransformationIDs, transformation.Group)
			}
			panels[id] = entry
			continue
		}
		if element.LibraryPanelKind != nil {
			panel := element.LibraryPanelKind.Spec
			id := numberString(panel.Id)
			panels[id] = sourcePanelAudit{ID: id, LibraryElementUID: panel.LibraryPanel.Uid}
		}
	}
	return stats, panels
}

func layoutElementReferences(layout any) ([]string, error) {
	data, err := json.Marshal(layout)
	if err != nil {
		return nil, err
	}
	var value any
	if err := json.Unmarshal(data, &value); err != nil {
		return nil, err
	}
	var refs []string
	var walk func(any)
	walk = func(current any) {
		switch node := current.(type) {
		case []any:
			for _, child := range node {
				walk(child)
			}
		case map[string]any:
			if node["kind"] == "ElementReference" {
				if name, ok := node["name"].(string); ok {
					refs = append(refs, name)
				}
			}
			for _, child := range node {
				walk(child)
			}
		}
	}
	walk(value)
	return refs, nil
}

func numberString(value any) string {
	switch number := value.(type) {
	case float64:
		return strconv.FormatFloat(number, 'f', -1, 64)
	case float32:
		return strconv.FormatFloat(float64(number), 'f', -1, 32)
	case int:
		return strconv.Itoa(number)
	case int64:
		return strconv.FormatInt(number, 10)
	case json.Number:
		return number.String()
	default:
		return ""
	}
}
