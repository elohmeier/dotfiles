// Stable dashboard.grafana.app/v2 constructors.
//
// This library deliberately does not convert classic dashboards and does not
// invent datasource UIDs or plugin versions. Use grafana-dashboard convert
// for conversion through Grafana's implementation.
{
  resource(name, spec, namespace=null, labels={}, annotations={}):: {
    apiVersion: 'dashboard.grafana.app/v2',
    kind: 'Dashboard',
    metadata:
      { name: name }
      + (if namespace == null then {} else { namespace: namespace })
      + (if std.length(std.objectFields(labels)) == 0 then {} else { labels: labels })
      + (if std.length(std.objectFields(annotations)) == 0 then {} else { annotations: annotations }),
    spec: spec,
  },

  timeSettings(
    from='now-6h',
    to='now',
    timezone='browser',
    autoRefresh='',
    autoRefreshIntervals=['5s', '10s', '30s', '1m', '5m', '15m', '30m', '1h', '2h', '1d'],
    hideTimepicker=false,
    fiscalYearStartMonth=0
  )::
    {
      from: from,
      to: to,
      autoRefresh: autoRefresh,
      autoRefreshIntervals: autoRefreshIntervals,
      hideTimepicker: hideTimepicker,
      fiscalYearStartMonth: fiscalYearStartMonth,
    }
    + (if timezone == null then {} else { timezone: timezone }),

  spec(
    title,
    elements,
    layout,
    description=null,
    annotations=[],
    variables=[],
    links=[],
    tags=[],
    cursorSync='Off',
    editable=true,
    preload=false,
    timeSettings=$.timeSettings()
  )::
    {
      annotations: annotations,
      cursorSync: cursorSync,
      editable: editable,
      elements: elements,
      layout: layout,
      links: links,
      preload: preload,
      tags: tags,
      timeSettings: timeSettings,
      title: title,
      variables: variables,
    }
    + (if description == null then {} else { description: description }),

  datasource(uid):: { name: uid },

  dataQuery(group, datasourceUid, spec, version='v0', labels=null)::
    {
      kind: 'DataQuery',
      group: group,
      version: version,
      spec: spec,
    }
    + (if datasourceUid == null then {} else { datasource: $.datasource(datasourceUid) })
    + (if labels == null then {} else { labels: labels }),

  panelQuery(refId, query, hidden=false):: {
    kind: 'PanelQuery',
    spec: {
      query: query,
      refId: refId,
      hidden: hidden,
    },
  },

  transformation(group, options, disabled=null, filter=null, topic=null):: {
    kind: 'Transformation',
    group: group,
    spec:
      { options: options }
      + (if disabled == null then {} else { disabled: disabled })
      + (if filter == null then {} else { filter: filter })
      + (if topic == null then {} else { topic: topic }),
  },

  queryGroup(queries=[], transformations=[], queryOptions={}):: {
    kind: 'QueryGroup',
    spec: {
      queries: queries,
      transformations: transformations,
      queryOptions: queryOptions,
    },
  },

  fieldConfig(defaults={}, overrides=[]):: {
    defaults: defaults,
    overrides: overrides,
  },

  panel(
    id,
    title,
    pluginId,
    pluginVersion,
    data=$.queryGroup(),
    options={},
    fieldConfig=$.fieldConfig(),
    description=null,
    subtitle=null,
    links=[],
    transparent=null
  )::
    {
      kind: 'Panel',
      spec: {
        id: id,
        title: title,
        links: links,
        data: data,
        vizConfig: {
          kind: 'VizConfig',
          group: pluginId,
          version: pluginVersion,
          spec: {
            options: options,
            fieldConfig: fieldConfig,
          },
        },
      }
      + (if description == null then {} else { description: description })
      + (if subtitle == null then {} else { subtitle: subtitle })
      + (if transparent == null then {} else { transparent: transparent }),
    },

  libraryPanel(id, title, uid, name):: {
    kind: 'LibraryPanel',
    spec: {
      id: id,
      title: title,
      libraryPanel: {
        uid: uid,
        name: name,
      },
    },
  },

  elementReference(name):: {
    kind: 'ElementReference',
    name: name,
  },

  gridItem(name, x, y, width, height, repeat=null):: {
    kind: 'GridLayoutItem',
    spec:
      {
        x: x,
        y: y,
        width: width,
        height: height,
        element: $.elementReference(name),
      }
      + (if repeat == null then {} else { repeat: repeat }),
  },

  gridLayout(items):: {
    kind: 'GridLayout',
    spec: { items: items },
  },

  patchPanel(elements, name, specPatch)::
    elements {
      [name]+: {
        spec+: specPatch,
      },
    },
}
