"""Build the Power BI project (PBIP) from code: semantic model, DAX measures and two report pages.

The model reads the CSV exports straight from GitHub, so a refresh in Power BI Desktop
picks up the latest monthly run of the pipeline.

    python powerbi/build_report.py
Then open powerbi/NYC_Congestion.pbip in Power BI Desktop and click Refresh.
"""

import json
import shutil
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "NYC_Congestion"
SOURCE_URL = "https://raw.githubusercontent.com/Laraki-Yacout/nyc-congestion-pricing-pipeline/main/exports/"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
C = dict(page="#F3F5F8", card="#FFFFFF", border="#DDE3EA", navy="#1F3A5F", orange="#D9822B",
         text="#1B2733", grey="#5B6776", grid="#E8ECF1", steel="#5C7FA8")

# ---------------------------------------------------------------- semantic model
TABLES = {
    "fct_trips_hourly": [("pickup_date", "dateTime"), ("pickup_hour", "int64"), ("segment", "string"),
                         ("toll_period", "string"), ("trips", "int64"), ("distance_mi", "double"),
                         ("duration_min", "double"), ("fare_amount", "double"), ("tip_amount", "double"),
                         ("total_amount", "double"), ("cbd_fee", "double")],
    "fct_zone_monthly": [("month_start", "dateTime"), ("zone_id", "int64"), ("trips", "int64"),
                         ("distance_mi", "double"), ("duration_min", "double"), ("total_amount", "double"),
                         ("cbd_fee", "double")],
    "dim_date": [("date", "dateTime"), ("year", "int64"), ("month", "int64"), ("year_month", "string"),
                 ("month_name", "string"), ("iso_dow", "int64"), ("day_name", "string"),
                 ("is_weekend", "boolean"), ("is_after_toll", "boolean")],
    "dim_zones": [("zone_id", "int64"), ("borough", "string"), ("zone_name", "string"), ("service_zone", "string"),
                  ("trips_from_after_toll", "int64"), ("trips_to_after_toll", "int64"),
                  ("share_charged_from", "double"), ("share_charged_to", "double"), ("is_crz", "boolean")],
    "mart_toll_effect": [("comparison", "string"), ("method", "string"), ("scope", "string"), ("segment", "string"),
                         ("control_group", "string"), ("is_main_estimate", "boolean"), ("months_compared", "int64"),
                         ("treated_days", "int64"), ("baseline_days", "int64"), ("speed_effect_pct", "double"),
                         ("ci95_low_pct", "double"), ("ci95_high_pct", "double"), ("is_significant", "boolean")],
    "mart_toll_effect_monthly": [("month_start", "dateTime"), ("segment", "string"), ("control_group", "string"),
                                 ("trips", "int64"),
                                 ("speed_mph", "double"), ("control_speed_mph", "double"), ("speed_ratio", "double"),
                                 ("baseline_year", "int64"), ("baseline_speed_ratio", "double"),
                                 ("speed_effect_pct", "double"), ("trips_change_pct", "double"), ("period", "string")],
    "mart_speed_by_hour": [("year", "int64"), ("day_type", "string"), ("pickup_hour", "int64"),
                           ("segment", "string"), ("trips", "int64"), ("speed_mph", "double")],
    "mart_data_quality": [("file_month", "dateTime"), ("status", "string"), ("trips", "int64")],
}
SEGMENTS = [("within_zone", "Within the zone", 1), ("into_zone", "Into the zone", 2),
            ("out_of_zone", "Out of the zone", 3), ("outside_zone", "Outside the zone", 4)]
HIDDEN = {
    "fct_trips_hourly": {"pickup_date", "segment", "trips", "distance_mi", "duration_min", "fare_amount",
                         "tip_amount", "total_amount", "cbd_fee"},
    "fct_zone_monthly": {"month_start", "zone_id", "trips", "distance_mi", "duration_min", "total_amount", "cbd_fee"},
    "dim_date": {"month", "iso_dow"},
    "dim_segment": {"segment", "sort_order"},
}
M_TYPE = {"string": "type text", "int64": "Int64.Type", "dateTime": "type date", "double": "type number",
          "boolean": "type logical"}


def m_csv(table: str) -> list[str]:
    columns = TABLES[table]
    typed = ", ".join('{"%s", %s}' % (n, M_TYPE[d]) for n, d in columns)
    return [
        "let",
        f'    Source = Csv.Document(Web.Contents(SourceUrl, [RelativePath = "{table}.csv"]),',
        f'        [Delimiter = ",", Columns = {len(columns)}, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        '    EmptyAsNull = Table.TransformColumns(Headers, {}, each if _ = "" then null else _),',
        f'    Typed = Table.TransformColumnTypes(EmptyAsNull, {{{typed}}}, "en-US")',
        "in",
        "    Typed",
    ]


def m_segments() -> list[str]:
    rows = ", ".join('{"%s", "%s", %d}' % s for s in SEGMENTS)
    return ["let",
            f'    Source = #table(type table [segment = text, segment_label = text, sort_order = Int64.Type], {{{rows}}})',
            "in", "    Source"]


def effect(comparison: str, scope: str, main_only: bool = True) -> list[str]:
    lines = ["CALCULATE(", "    AVERAGE(mart_toll_effect[speed_effect_pct]),",
             f'    mart_toll_effect[segment] = "within_zone",']
    if comparison:
        lines.append(f'    mart_toll_effect[comparison] = "{comparison}",')
    if scope:
        lines.append(f'    mart_toll_effect[scope] = "{scope}",')
    if main_only:
        lines.append("    mart_toll_effect[is_main_estimate] = TRUE(),")
    lines[-1] = lines[-1].rstrip(",")
    return lines + [")"]


PCT = '+0.0%;-0.0%;0.0%'
MEASURES = {
    "fct_trips_hourly": [
        ("Total trips", ["SUM(fct_trips_hourly[trips])"], "#,0"),
        ("Revenue", ["SUM(fct_trips_hourly[total_amount])"], '"$"#,0'),
        ("Average fare", ["DIVIDE(SUM(fct_trips_hourly[fare_amount]), [Total trips])"], '"$"#,0.00'),
        ("Average speed (mph)", ["DIVIDE(SUM(fct_trips_hourly[distance_mi]), SUM(fct_trips_hourly[duration_min]) / 60)"], "0.0"),
        ("Average trip time (min)", ["DIVIDE(SUM(fct_trips_hourly[duration_min]), [Total trips])"], "0.0"),
        ("Congestion fees paid", ["SUM(fct_trips_hourly[cbd_fee])"], '"$"#,0'),
        ("Trips vs previous year", ["VAR Previous = CALCULATE([Total trips], DATEADD(dim_date[date], -1, YEAR))",
                                    "RETURN DIVIDE([Total trips] - Previous, Previous)"], PCT),
        ("Data up to", ['FORMAT(CALCULATE(MAX(fct_trips_hourly[pickup_date]), ALL(fct_trips_hourly)), "mmm yyyy")'], None),
    ],
    "mart_toll_effect": [
        ("Speed gain in the zone, 2025", effect("2025 vs 2024", "all hours"), PCT),
        ("Peak hours, 2025", effect("2025 vs 2024", "peak hours"), PCT),
        ("2026 so far", effect("2026 vs 2024", "all hours"), PCT),
        ("Placebo, 2024 vs 2023", effect("placebo: 2024 vs 2023", "all hours"), PCT),
        ("Effect 2025 vs 2024", effect("2025 vs 2024", None), PCT),
        ("Effect 2025 with this control", effect("2025 vs 2024", "all hours", main_only=False), PCT),
        ("Trend-adjusted, 2025", effect("2025 vs 2024, trend-adjusted", "all hours", main_only=False), PCT),
    ],
    "mart_toll_effect_monthly": [
        ("Zone speed vs rest of city", ['CALCULATE(AVERAGE(mart_toll_effect_monthly[speed_ratio]), '
                                        'mart_toll_effect_monthly[segment] = "within_zone")'], "0.0%"),
    ],
    "mart_speed_by_hour": [
        ("Weekday speed in the zone (mph)", ["CALCULATE(", "    AVERAGE(mart_speed_by_hour[speed_mph]),",
                                             '    mart_speed_by_hour[segment] = "within_zone",',
                                             '    mart_speed_by_hour[day_type] = "weekday",',
                                             "    KEEPFILTERS(mart_speed_by_hour[year] IN {2024, 2025})", ")"], "0.0"),
    ],
    "mart_data_quality": [
        ("Rows kept after checks", ['DIVIDE(CALCULATE(SUM(mart_data_quality[trips]), mart_data_quality[status] = "kept"), '
                                    "SUM(mart_data_quality[trips]))"], "0.0%"),
    ],
    "fct_zone_monthly": [
        ("Zone trips", ["SUM(fct_zone_monthly[trips])"], "#,0"),
        ("Top 10 pickup zones", ["VAR ZoneRank = RANKX(ALLSELECTED(dim_zones[zone_name]), [Zone trips], , DESC, Skip)",
                                 "RETURN IF(NOT ISBLANK([Zone trips]) && ZoneRank <= 10, [Zone trips])"], "#,0"),
    ],
}


def column(table: str, name: str, dtype: str) -> dict:
    col = {"name": name, "dataType": dtype, "sourceColumn": name, "summarizeBy": "none",
           "annotations": [{"name": "SummarizationSetBy", "value": "Automatic"}]}
    if dtype == "dateTime":
        col["formatString"] = "yyyy-mm-dd"
    if name.endswith("_pct") or name.startswith("share_") or name == "speed_ratio":
        col["formatString"] = "0.0%"
    if name in HIDDEN.get(table, ()):
        col["isHidden"] = True
    if (table, name) == ("dim_date", "date"):
        col["isKey"] = True
    if (table, name) == ("dim_segment", "segment_label"):
        col["sortByColumn"] = "sort_order"
    return col


def build_model() -> dict:
    tables = []
    all_tables = dict(TABLES)
    all_tables["dim_segment"] = [("segment", "string"), ("segment_label", "string"), ("sort_order", "int64")]
    for table, columns in all_tables.items():
        expression = m_segments() if table == "dim_segment" else m_csv(table)
        entry = {"name": table, "columns": [column(table, n, d) for n, d in columns],
                 "partitions": [{"name": table, "mode": "import", "source": {"type": "m", "expression": expression}}],
                 "annotations": [{"name": "PBI_ResultType", "value": "Table"}]}
        if table == "dim_date":
            entry["dataCategory"] = "Time"
        if table in MEASURES:
            entry["measures"] = []
            for name, expr, fmt in MEASURES[table]:
                measure = {"name": name, "expression": expr if len(expr) > 1 else expr[0]}
                if fmt:
                    measure["formatString"] = fmt
                entry["measures"].append(measure)
        tables.append(entry)

    relationships = [
        ("fct_trips_hourly", "pickup_date", "dim_date", "date"),
        ("fct_trips_hourly", "segment", "dim_segment", "segment"),
        ("fct_zone_monthly", "month_start", "dim_date", "date"),
        ("fct_zone_monthly", "zone_id", "dim_zones", "zone_id"),
    ]
    return {"compatibilityLevel": 1567, "model": {
        "culture": "en-US", "defaultPowerBIDataSourceVersion": "powerBI_V3", "sourceQueryCulture": "en-US",
        "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
        "tables": tables,
        "relationships": [{"name": str(uuid.uuid5(uuid.NAMESPACE_URL, f + fc + t)), "fromTable": f, "fromColumn": fc,
                           "toTable": t, "toColumn": tc} for f, fc, t, tc in relationships],
        "expressions": [{"name": "SourceUrl", "kind": "m",
                         "expression": json.dumps(SOURCE_URL) + ' meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
                         "annotations": [{"name": "PBI_ResultType", "value": "Text"}]}],
        "annotations": [{"name": "PBI_ProTooling", "value": '["DevMode"]'},
                        {"name": "__PBI_TimeIntelligenceEnabled", "value": "0"},
                        {"name": "PBI_QueryOrder", "value": json.dumps(["SourceUrl", *all_tables])}]}}


# ---------------------------------------------------------------- report helpers
def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8", newline="\n")


def lit(v): return {"expr": {"Literal": {"Value": v}}}
def s(v): return lit("'" + v.replace("'", "''") + "'")
def solid(c): return {"solid": {"color": s(c)}}
def measure_ref(table, n): return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": n}}
def column_ref(table, n): return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": n}}


def pm(table, n, **k):
    return {"field": measure_ref(table, n), "queryRef": f"{table}.{n}", "nativeQueryRef": n, **k}


def pc(table, n, **k):
    return {"field": column_ref(table, n), "queryRef": f"{table}.{n}", "nativeQueryRef": n, "active": True, **k}


def container(title, alt):
    objects = {"general": [{"properties": {"altText": s(alt)}}],
               "background": [{"properties": {"show": lit("true"), "color": solid(C["card"]), "transparency": lit("0D")}}],
               "border": [{"properties": {"show": lit("true"), "color": solid(C["border"]), "radius": lit("8D"), "width": lit("1D")}}],
               "visualHeader": [{"properties": {"show": lit("false")}}]}
    objects["title"] = ([{"properties": {"show": lit("true"), "text": s(title), "fontSize": lit("11D"), "bold": lit("true"),
                                         "fontColor": solid(C["text"]), "alignment": s("left")}}]
                        if title else [{"properties": {"show": lit("false")}}])
    return objects


class Page:
    def __init__(self, folder: Path, name: str, display: str):
        self.dir, self.name, self.count = folder / name, name, 0
        write(self.dir / "page.json", {
            "$schema": f"{SCHEMA}/item/report/definition/page/1.2.0/schema.json", "name": name,
            "displayName": display, "displayOption": "FitToPage", "height": 720, "width": 1280,
            "objects": {"background": [{"properties": {"color": solid(C["page"]), "transparency": lit("0D")}}],
                        "outspace": [{"properties": {"color": solid(C["page"]), "transparency": lit("0D")}}]}})

    def visual(self, name, x, y, w, h, visual):
        self.count += 1
        write(self.dir / f"visuals/{name}/visual.json", {
            "$schema": f"{SCHEMA}/item/report/definition/visualContainer/1.3.0/schema.json", "name": name,
            "position": {"x": x, "y": y, "z": self.count * 100, "width": w, "height": h, "tabOrder": self.count * 100},
            "visual": visual})

    def text(self, name, x, y, w, h, paragraphs, alt):
        self.visual(name, x, y, w, h, {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]},
                    "visualContainerObjects": {"general": [{"properties": {"altText": s(alt)}}],
                                               "background": [{"properties": {"show": lit("false")}}],
                                               "visualHeader": [{"properties": {"show": lit("false")}}]},
                    "drillFilterOtherVisuals": True})

    def title(self, title, subtitle):
        self.text("title", 16, 12, 1000, 56, [
            {"textRuns": [{"value": title, "textStyle": {"fontWeight": "bold", "fontSize": "20pt", "color": C["text"]}}]},
            {"textRuns": [{"value": subtitle, "textStyle": {"fontSize": "10pt", "color": C["grey"]}}]}], "Page title")

    def footer(self, text):
        self.text("source_note", 16, 694, 1248, 22,
                  [{"textRuns": [{"value": text, "textStyle": {"fontSize": "8pt", "color": C["grey"]}}]}], "Source note")

    def card(self, name, x, y, w, table, measure, alt, color=None, size="24D", h=88):
        self.visual(name, x, y, w, h, {
            "visualType": "card", "query": {"queryState": {"Values": {"projections": [pm(table, measure)]}}},
            "objects": {"labels": [{"properties": {"color": solid(color or C["navy"]), "fontSize": lit(size),
                                                   "labelDisplayUnits": lit("1D")}}],
                        "categoryLabels": [{"properties": {"show": lit("true"), "color": solid(C["grey"]), "fontSize": lit("10D")}}]},
            "visualContainerObjects": container(None, alt), "drillFilterOtherVisuals": True})

    def chart(self, name, x, y, w, h, kind, title, alt, category, values, series=None, color=C["navy"],
              sort=None, labels=True, legend=False):
        state = {"Category": {"projections": [category]}, "Y": {"projections": values}}
        if series:
            state["Series"] = {"projections": [series]}
        query = {"queryState": state}
        if sort:
            query["sortDefinition"] = {"sort": [sort], "isDefaultSort": True}
        objects = {
            "categoryAxis": [{"properties": {"showAxisTitle": lit("false"), "fontSize": lit("9D"),
                                             "labelColor": solid(C["grey"])}}],
            "valueAxis": [{"properties": {"showAxisTitle": lit("false"), "fontSize": lit("9D"),
                                          "labelColor": solid(C["grey"]), "gridlineColor": solid(C["grid"])}}],
            "legend": [{"properties": {"show": lit("true" if series or legend else "false"), "position": s("Top"),
                                       "fontSize": lit("9D")}}],
        }
        if not series and not legend:
            objects["dataPoint"] = [{"properties": {"fill": solid(color)}}]
        if kind == "lineChart":
            objects["lineStyles"] = [{"properties": {"strokeWidth": lit("2D"), "showMarker": lit("true"), "markerSize": lit("3D")}}]
        if labels and kind != "lineChart":
            objects["labels"] = [{"properties": {"show": lit("true"), "fontSize": lit("9D"), "color": solid(C["grey"])}}]
        self.visual(name, x, y, w, h, {"visualType": kind, "query": query, "objects": objects,
                                       "visualContainerObjects": container(title, alt), "drillFilterOtherVisuals": True})

    def slicer(self, name, x, y, w, h, table, col, label):
        self.visual(name, x, y, w, h, {
            "visualType": "slicer", "query": {"queryState": {"Values": {"projections": [pc(table, col, displayName=label)]}}},
            "objects": {"data": [{"properties": {"mode": s("Dropdown")}}],
                        "header": [{"properties": {"show": lit("true"), "fontColor": solid(C["grey"]), "textSize": lit("10D")}}]},
            "visualContainerObjects": {"general": [{"properties": {"altText": s(f"Filter by {label.lower()}")}}],
                                       "background": [{"properties": {"show": lit("false")}}],
                                       "visualHeader": [{"properties": {"show": lit("false")}}]},
            "drillFilterOtherVisuals": True})


SOURCE_NOTE = ("Source: NYC Taxi & Limousine Commission yellow taxi trip records (NYC Open Data), refreshed monthly by the pipeline. "
               "Zone = Congestion Relief Zone, inferred from the $0.75 fee. Personal portfolio project.")


def build_pages(definition: Path) -> list[str]:
    pages = definition / "pages"

    # Page 1: the question
    p = Page(pages, "toll_effect", "Did the toll speed up traffic?")
    p.title("Did Manhattan's congestion toll speed up traffic?",
            "Yellow taxis as traffic sensors: speed inside the toll zone compared with the rest of the city, before and after 5 Jan 2025")
    p.card("data_up_to", 1064, 14, 200, "fct_trips_hourly", "Data up to", "Last month of data", C["grey"], "14D", h=58)
    p.card("kpi_effect_2025", 16, 80, 302, "mart_toll_effect", "Speed gain in the zone, 2025",
           "Difference-in-differences estimate for 2025, all hours", C["orange"])
    p.card("kpi_effect_peak", 330, 80, 302, "mart_toll_effect", "Peak hours, 2025",
           "Estimate for 2025, peak toll hours")
    p.card("kpi_effect_2026", 644, 80, 302, "mart_toll_effect", "2026 so far", "Estimate for 2026 so far")
    p.card("kpi_placebo", 958, 80, 306, "mart_toll_effect", "Placebo, 2024 vs 2023",
           "Placebo estimate with no toll, should be close to zero", C["grey"])
    p.chart("monthly_gap", 16, 180, 820, 300, "lineChart",
            "Speed inside the zone, as a % of short trips outside it (monthly)",
            "Monthly speed ratio between trips within the zone and trips outside it",
            pc("mart_toll_effect_monthly", "month_start", displayName="Month"),
            [pm("mart_toll_effect_monthly", "Zone speed vs rest of city")],
            sort={"field": column_ref("mart_toll_effect_monthly", "month_start"), "direction": "Ascending"})
    p.chart("effect_by_time", 848, 180, 416, 300, "clusteredColumnChart",
            "Estimated speed gain by time of day, 2025 vs 2024",
            "Difference-in-differences estimate for all hours, peak and overnight hours",
            pc("mart_toll_effect", "scope", displayName="Time of day"),
            [pm("mart_toll_effect", "Effect 2025 vs 2024")], color=C["orange"],
            sort={"field": column_ref("mart_toll_effect", "scope"), "direction": "Ascending"})
    p.chart("robustness", 16, 492, 620, 196, "clusteredBarChart",
            "Robustness: 2025 estimate with each control group",
            "2025 estimate with each of the four control groups, simple and trend-adjusted",
            pc("mart_toll_effect", "control_group", displayName="Control group"),
            [pm("mart_toll_effect", "Effect 2025 with this control"), pm("mart_toll_effect", "Trend-adjusted, 2025")],
            color=C["steel"], legend=True)
    p.chart("speed_by_hour", 648, 492, 616, 196, "lineChart",
            "Weekday speed inside the zone by hour (mph), 2024 vs 2025",
            "Average weekday speed inside the zone by hour of day for 2024 and 2025",
            pc("mart_speed_by_hour", "pickup_hour", displayName="Hour"),
            [pm("mart_speed_by_hour", "Weekday speed in the zone (mph)")],
            series=pc("mart_speed_by_hour", "year", displayName="Year"),
            sort={"field": column_ref("mart_speed_by_hour", "pickup_hour"), "direction": "Ascending"})
    p.footer(SOURCE_NOTE)

    # Page 2: the business view
    q = Page(pages, "taxi_activity", "Taxi activity")
    q.title("NYC yellow taxi activity", "Trips, revenue and congestion fees, by month and by relation to the toll zone")
    q.slicer("year_filter", 1064, 14, 200, 50, "dim_date", "year", "Year")
    q.card("kpi_trips", 16, 80, 302, "fct_trips_hourly", "Total trips", "Number of valid trips")
    q.card("kpi_revenue", 330, 80, 302, "fct_trips_hourly", "Revenue", "Total amount paid by passengers")
    q.card("kpi_fare", 644, 80, 302, "fct_trips_hourly", "Average fare", "Average metered fare per trip")
    q.card("kpi_fees", 958, 80, 306, "fct_trips_hourly", "Congestion fees paid",
           "Congestion fees paid by taxi passengers", C["orange"])
    q.chart("trips_by_month", 16, 180, 820, 300, "columnChart", "Trips per month by relation to the toll zone",
            "Monthly trips stacked by segment",
            pc("dim_date", "year_month", displayName="Month"), [pm("fct_trips_hourly", "Total trips")],
            series=pc("dim_segment", "segment_label", displayName="Segment"),
            sort={"field": column_ref("dim_date", "year_month"), "direction": "Ascending"}, labels=False)
    q.chart("speed_by_segment", 848, 180, 416, 300, "clusteredBarChart", "Average speed by segment (mph)",
            "Average speed for each segment",
            pc("dim_segment", "segment_label", displayName="Segment"), [pm("fct_trips_hourly", "Average speed (mph)")],
            sort={"field": column_ref("dim_segment", "segment_label"), "direction": "Ascending"})
    q.chart("top_zones", 16, 492, 620, 196, "clusteredBarChart", "Top 10 pickup zones",
            "Ten pickup zones with the most trips",
            pc("dim_zones", "zone_name", displayName="Zone"), [pm("fct_zone_monthly", "Top 10 pickup zones")],
            sort={"field": measure_ref("fct_zone_monthly", "Top 10 pickup zones"), "direction": "Descending"})
    q.chart("fees_by_month", 648, 492, 444, 196, "columnChart", "Congestion fees paid by taxi passengers, by month",
            "Monthly congestion fees paid by taxi passengers",
            pc("dim_date", "year_month", displayName="Month"), [pm("fct_trips_hourly", "Congestion fees paid")],
            color=C["orange"], sort={"field": column_ref("dim_date", "year_month"), "direction": "Ascending"},
            labels=False)
    q.card("kpi_quality", 1104, 492, 160, "mart_data_quality", "Rows kept after checks",
           "Share of raw rows kept after the quality checks", C["grey"], "18D", h=196)
    q.footer(SOURCE_NOTE)
    return [p.name, q.name]


def main() -> None:
    semantic, report = HERE / f"{NAME}.SemanticModel", HERE / f"{NAME}.Report"
    for folder in (semantic, report):
        if folder.exists():
            shutil.rmtree(folder)
    platform = f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json"
    write(semantic / "model.bim", build_model())
    write(semantic / "definition.pbism", {"$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
                                          "version": "4.0", "settings": {}})
    write(semantic / ".platform", {"$schema": platform, "metadata": {"type": "SemanticModel", "displayName": NAME},
                                   "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, NAME + "sm"))}})
    write(report / ".platform", {"$schema": platform, "metadata": {"type": "Report", "displayName": NAME},
                                 "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, NAME + "rp"))}})
    write(report / "definition.pbir", {"$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
                                       "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    write(HERE / f"{NAME}.pbip", {"$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
                                  "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                                  "settings": {"enableAutoRecovery": True}})
    write(HERE / ".gitignore", "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
    themes = report / "StaticResources/SharedResources/BaseThemes"
    themes.mkdir(parents=True)
    shutil.copy(HERE / "theme/CY24SU10.json", themes / "CY24SU10.json")

    definition = report / "definition"
    base = f"{SCHEMA}/item/report/definition"
    write(definition / "version.json", {"$schema": f"{base}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    write(definition / "report.json", {
        "$schema": f"{base}/report/1.2.0/schema.json",
        "themeCollection": {"baseTheme": {"name": "CY24SU10", "reportVersionAtImport": "5.59", "type": "SharedResources"}},
        "layoutOptimization": "None", "objects": {"section": [{"properties": {"verticalAlignment": s("Top")}}]},
        "resourcePackages": [{"name": "SharedResources", "type": "SharedResources",
                              "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                     "allowChangeFilterTypes": True, "useDefaultAggregateDisplayName": True}})
    pages = build_pages(definition)
    write(definition / "pages/pages.json", {"$schema": f"{base}/pagesMetadata/1.0.0/schema.json",
                                            "pageOrder": pages, "activePageName": pages[0]})
    print(f"Power BI project written to {HERE / (NAME + '.pbip')}")


if __name__ == "__main__":
    main()
