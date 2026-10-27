// Stable dashboard.grafana.app/v2 Prometheus authoring helpers.
// Datasource defaults are configuration supplied by the consumer.
{
  // Override with withDefaultDatasource(), or pass datasourceUid explicitly.
  defaultDatasourceUid:: error 'datasourceUid is required',
  withDefaultDatasource(uid):: self { defaultDatasourceUid: uid },

  promqlTitle(title)::
    local suffix = ' (PromQL)';
    if std.length(title) >= std.length(suffix) &&
       std.substr(title, std.length(title) - std.length(suffix), std.length(suffix)) == suffix
    then title
    else title + suffix,

  datasource(uid=$.defaultDatasourceUid):: {
    name: uid,
  },

  current(text, value=text):: {
    text: text,
    value: value,
  },

  labelFilter(label, value, operator='=~')::
    std.format('%s%s"%s"', [label, operator, value]),

  labelSelector(filters):: '{' + std.join(', ', filters) + '}',

  panelQuery(
    refId,
    expr,
    datasourceUid=$.defaultDatasourceUid,
    legendFormat=null,
    format=null,
    instant=false,
    hidden=false
  ):: {
    kind: 'PanelQuery',
    spec: {
      refId: refId,
      hidden: hidden,
      query: {
        kind: 'DataQuery',
        group: 'prometheus',
        version: 'v0',
        datasource: $.datasource(datasourceUid),
        spec:
          {
            editorMode: 'code',
            exemplar: false,
            expr: expr,
            fullMetaSearch: false,
            includeNullMetadata: true,
            range: !instant,
            useBackend: false,
          }
          + (if legendFormat == null then {} else { legendFormat: legendFormat })
          + (if format == null then {} else { format: format })
          + (if instant then { instant: true } else {}),
      },
    },
  },

  target(expr, legendFormat='', refId='A', datasourceUid=$.defaultDatasourceUid):: $.panelQuery(
    refId,
    expr,
    datasourceUid=datasourceUid,
    legendFormat=if legendFormat == '' then null else legendFormat
  ),

  instantTarget(expr, legendFormat='', refId='A', datasourceUid=$.defaultDatasourceUid):: $.panelQuery(
    refId,
    expr,
    datasourceUid=datasourceUid,
    legendFormat=if legendFormat == '' then null else legendFormat,
    instant=true
  ),

  tableTarget(expr, refId='A', datasourceUid=$.defaultDatasourceUid):: $.panelQuery(
    refId,
    expr,
    datasourceUid=datasourceUid,
    format='table',
    instant=true
  ),

  queryGroup(queries, transformations=[], queryOptions={}):: {
    kind: 'QueryGroup',
    spec: {
      queries: queries,
      transformations: transformations,
      queryOptions: queryOptions,
    },
  },

  panelData(queries, transformations=[], queryOptions={}):: {
    data: $.queryGroup(queries, transformations, queryOptions),
  },

  labelsToFields():: {
    kind: 'Transformation',
    group: 'labelsToFields',
    spec: {
      options: {
        mode: 'columns',
      },
    },
  },

  byRefId(refIdOrPattern):: {
    id: 'byRefId',
    options: refIdOrPattern,
  },

  mergedRefIdPattern(refId):: '/^(?:' + refId + '|merge-' + refId + '(?:-' + refId + ')*)$/',

  mergeByRefId(refId):: {
    kind: 'Transformation',
    group: 'merge',
    spec: {
      filter: $.byRefId(refId),
      options: {},
    },
  },

  organizeMetricByRefId(refId, displayName, excludeByName={}):: {
    kind: 'Transformation',
    group: 'organize',
    spec: {
      filter: $.byRefId($.mergedRefIdPattern(refId)),
      options: {
        excludeByName: excludeByName,
        renameByName: { Value: displayName },
      },
    },
  },

  joinByField(field, mode='outer'):: {
    kind: 'Transformation',
    group: 'joinByField',
    spec: {
      options: {
        byField: field,
        mode: mode,
      },
    },
  },

  // Use after one instant/table query per numeric column. Each column is
  // { refId: 'A', displayName: 'State' }. Append a final organize transform.
  metricTableTransforms(columns, joinField='source', excludeByName={})::
    [$.labelsToFields()]
    + [
      transform
      for column in columns
      for transform in [
        $.mergeByRefId(column.refId),
        $.organizeMetricByRefId(column.refId, column.displayName, excludeByName),
      ]
    ]
    + [$.joinByField(joinField)],

  filterFieldsByName(names):: {
    kind: 'Transformation',
    group: 'filterFieldsByName',
    spec: {
      options: {
        include: {
          names: names,
        },
      },
    },
  },

  organize(names, renameByName={}):: {
    kind: 'Transformation',
    group: 'organize',
    spec: {
      options: {
        includeByName: {
          [name]: true
          for name in names
        },
        indexByName: {
          [item.name]: item.index
          for item in std.mapWithIndex(function(index, name) { index: index, name: name }, names)
        },
        renameByName: renameByName,
      },
    },
  },

  // Single-query table shaping only. For different metrics, use
  // metricTableTransforms with one query per numeric column.
  tablePivot(names):: [
    $.labelsToFields(),
    $.filterFieldsByName(names),
    $.organize(names),
  ],

  timeSeriesPanel(queries):: $.panelData(queries),

  patchPanel(name, specPatch):: {
    elements+: {
      [name]+: {
        spec+: specPatch,
      },
    },
  },

  thresholdStep(color, value=0):: {
    color: color,
    value: value,
  },

  thresholds(steps, mode='absolute'):: {
    mode: mode,
    steps: steps,
  },

  fieldOverride(matcherId, matcherOptions, properties):: {
    matcher: {
      id: matcherId,
      options: matcherOptions,
    },
    properties: properties,
  },

  byNameOverride(name, properties):: $.fieldOverride('byName', name, properties),

  byRegexpOverride(pattern, properties):: $.fieldOverride('byRegexp', pattern, properties),

  fieldProperty(id, value):: {
    id: id,
    value: value,
  },

  widthOverride(name, width):: $.byNameOverride(name, [$.fieldProperty('custom.width', width)]),

  unitOverride(name, unit):: $.byNameOverride(name, [$.fieldProperty('unit', unit)]),

  filterableOverride(name, enabled=true):: $.byNameOverride(
    name,
    [$.fieldProperty('custom.filterable', enabled)]
  ),

  mappingOverride(name, mappings):: $.byNameOverride(name, [$.fieldProperty('mappings', mappings)]),

  thresholdsOverride(name, thresholds):: $.byNameOverride(name, [$.fieldProperty('thresholds', thresholds)]),

  tableCellOptions(type='auto', wrapText=false):: {
    type: type,
    wrapText: wrapText,
  },

  queryVariable(
    name,
    query,
    current,
    label='',
    datasourceUid=$.defaultDatasourceUid,
    multi=false,
    includeAll=false,
    hide='dontHide',
    refresh='onDashboardLoad',
    sort='disabled',
    regex='',
    allValue=null,
    allowCustomValue=true,
    description=null
  ):: {
    kind: 'QueryVariable',
    spec:
      {
        name: name,
        current: current,
        label: label,
        hide: hide,
        refresh: refresh,
        skipUrlSync: false,
        query: {
          kind: 'DataQuery',
          group: 'prometheus',
          version: 'v0',
          datasource: $.datasource(datasourceUid),
          spec: {
            __legacyStringValue: query,
          },
        },
        definition: query,
        regex: regex,
        regexApplyTo: 'value',
        sort: sort,
        options: [],
        multi: multi,
        includeAll: includeAll,
        allowCustomValue: allowCustomValue,
      }
      + (if allValue == null then {} else { allValue: allValue })
      + (if description == null then {} else { description: description }),
  },

  datasourceVariable(
    name,
    pluginId='prometheus',
    current=null,
    label='',
    hide='dontHide',
    regex='',
    multi=false,
    includeAll=false
  ):: {
    kind: 'DatasourceVariable',
    spec: {
      name: name,
      pluginId: pluginId,
      refresh: 'onDashboardLoad',
      regex: regex,
      current: if current == null then { text: '', value: '' } else current,
      options: [],
      multi: multi,
      includeAll: includeAll,
      label: label,
      hide: hide,
      skipUrlSync: false,
      allowCustomValue: true,
    },
  },

  customVariable(
    name,
    query,
    current,
    label='',
    multi=false,
    includeAll=false,
    allValue=null,
    hide='dontHide'
  ):: {
    kind: 'CustomVariable',
    spec:
      {
        name: name,
        current: current,
        hide: hide,
        includeAll: includeAll,
        multi: multi,
        options: [],
        query: query,
        skipUrlSync: false,
        label: label,
        allowCustomValue: true,
      }
      + (if allValue == null then {} else { allValue: allValue }),
  },

  textVariable(name, query, label='', hide='dontHide'):: {
    kind: 'TextVariable',
    spec: {
      name: name,
      current: {
        text: query,
        value: query,
      },
      hide: hide,
      query: query,
      skipUrlSync: false,
      label: label,
    },
  },

  constantVariable(name, query, label='', hide='hideVariable'):: {
    kind: 'ConstantVariable',
    spec: {
      name: name,
      current: {
        text: query,
        value: query,
      },
      hide: hide,
      query: query,
      skipUrlSync: true,
      label: label,
    },
  },

  withoutKeys(obj, keys):: {
    [key]: obj[key]
    for key in std.objectFields(obj)
    if !std.member(keys, key)
  },
}
