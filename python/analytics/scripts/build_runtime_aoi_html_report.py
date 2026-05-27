from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path


def _parse_float(value: str | None, default: float = -1.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_int(value: str | None, default: int = -1) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _read_rows(csv_path: Path) -> list[dict[str, object]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, object]] = []
        for raw_row in reader:
            fixation_steps = _parse_int(raw_row.get("fixation_steps"))
            dwell_time_ms = _parse_float(raw_row.get("dwell_time_ms"))
            time_to_first_fixation_ms = _parse_float(raw_row.get("time_to_first_fixation_ms"))
            visit_count = _parse_int(raw_row.get("visit_count"))
            fb_count = _parse_int(raw_row.get("fb_count"))
            was_visited = _parse_int(raw_row.get("was_visited"), default=1)
            has_revisits = _parse_int(raw_row.get("has_revisits"), default=0)

            fd_ms = -1.0
            if fixation_steps > 0 and dwell_time_ms >= 0:
                fd_ms = round(dwell_time_ms / fixation_steps, 3)

            rows.append(
                {
                    "participant_id": raw_row.get("participant_id", ""),
                    "video_id": raw_row.get("video_id", ""),
                    "aoi_id": _parse_int(raw_row.get("aoi_id")),
                    "aoi_name": raw_row.get("aoi_name", ""),
                    "aoi_category": raw_row.get("aoi_category", ""),
                    "aoi_prompt": raw_row.get("aoi_prompt", ""),
                    "aoi_color": raw_row.get("aoi_color", ""),
                    "was_visited": was_visited,
                    "fb_count": fb_count,
                    "fixation_steps": fixation_steps,
                    "fc": fixation_steps,
                    "dwell_time_ms": dwell_time_ms,
                    "tfd_ms": dwell_time_ms,
                    "time_to_first_fixation_ms": time_to_first_fixation_ms,
                    "tff_ms": time_to_first_fixation_ms,
                    "fd_ms": fd_ms,
                    "visit_count": visit_count,
                    "has_revisits": 1 if has_revisits == 1 else 0,
                }
            )

    return rows


def _build_html(title: str, rows: list[dict[str, object]], source_csv: str) -> str:
    dataset_json = json.dumps(rows, ensure_ascii=False)
    title_escaped = html.escape(title)
    source_csv_escaped = html.escape(source_csv)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title_escaped}</title>
  <style>
    :root {{
      --bg: #f5f1e8;
      --panel: #fffdf8;
      --ink: #1f1d1a;
      --muted: #6b6258;
      --line: #d8cfbf;
      --accent: #2f6fed;
      --accent-soft: #dfe9ff;
      --pre: #f3f8ff;
      --sustained: #faf2e5;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      background: linear-gradient(180deg, #f7f3eb 0%, #f1ece1 100%);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1480px;
      margin: 0 auto;
      padding: 28px 24px 40px;
    }}
    .hero, .filters, .cards, .table-panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 12px 30px rgba(39, 32, 18, 0.05);
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 30px;
      line-height: 1.1;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      font-size: 15px;
    }}
    .filters-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    label {{
      display: block;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    select, input {{
      width: 100%;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }}
    .cards-top {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }}
    .cards-groups {{
      display: grid;
      grid-template-columns: 1fr 1.6fr;
      gap: 12px;
    }}
    .group {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
    }}
    .group.pre {{
      background: var(--pre);
    }}
    .group.sustained {{
      background: var(--sustained);
    }}
    .group-title {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 800;
      color: var(--muted);
      margin-bottom: 10px;
    }}
    .cards-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .cards-grid.wide {{
      grid-template-columns: repeat(5, minmax(0, 1fr));
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      background: rgba(255, 255, 255, 0.78);
    }}
    .card .k {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
      margin-bottom: 8px;
      font-weight: 700;
    }}
    .card .v {{
      font-size: 24px;
      font-weight: 800;
    }}
    .toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .toolbar .note {{
      color: var(--muted);
      font-size: 13px;
    }}
    .table-wrap {{
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fff;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 1320px;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid #ebe3d6;
      text-align: left;
      font-size: 13px;
      white-space: nowrap;
    }}
    thead th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: #fcf7ef;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
    }}
    thead tr.group-row th {{
      background: #f6efe2;
      text-align: center;
    }}
    thead tr.group-row th.pre-head {{
      background: #eaf2ff;
    }}
    thead tr.group-row th.sustained-head {{
      background: #f7ecd9;
    }}
    tbody tr:hover {{
      background: #f7fbff;
    }}
    .summary-row {{
      background: #f6efe2;
      font-weight: 700;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 4px 9px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: #1747aa;
      font-weight: 700;
      font-size: 12px;
    }}
    .dot {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
      border: 1px solid rgba(0,0,0,0.12);
      display: inline-block;
    }}
    .empty {{
      padding: 32px;
      text-align: center;
      color: var(--muted);
      font-weight: 600;
    }}
    .checkbox-cell {{
      text-align: center;
    }}
    .checkbox-cell input {{
      width: 16px;
      height: 16px;
      accent-color: var(--accent);
    }}
    .neg {{
      color: #8f8375;
    }}
    @media (max-width: 1080px) {{
      .filters-grid, .cards-top {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .cards-groups {{
        grid-template-columns: 1fr;
      }}
      .cards-grid.wide {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 640px) {{
      .wrap {{ padding: 18px 14px 28px; }}
      .filters-grid, .cards-top, .cards-grid, .cards-grid.wide {{
        grid-template-columns: 1fr;
      }}
      h1 {{ font-size: 24px; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>{title_escaped}</h1>
      <p class="subtitle">Visor HTML de Phase 3 generado desde <code>{source_csv_escaped}</code>. Las AOI no visitadas se muestran con <code>-1</code> y las metricas se ordenan como pre-atentivas (izquierda) y sostenidas (derecha).</p>
    </section>

    <section class="filters">
      <div class="filters-grid">
        <div>
          <label for="participantFilter">Participante</label>
          <select id="participantFilter"></select>
        </div>
        <div>
          <label for="videoFilter">Estimulo</label>
          <select id="videoFilter"></select>
        </div>
        <div>
          <label for="aoiFilter">AOI</label>
          <select id="aoiFilter"></select>
        </div>
        <div>
          <label for="searchFilter">Buscar texto</label>
          <input id="searchFilter" type="text" placeholder="p.ej. person_02 o lion">
        </div>
      </div>
    </section>

    <section class="cards">
      <div class="cards-top">
        <div class="card"><div class="k">Filas visibles</div><div id="cardRows" class="v">0</div></div>
        <div class="card"><div class="k">Participantes</div><div id="cardParticipants" class="v">0</div></div>
        <div class="card"><div class="k">Estimulos</div><div id="cardVideos" class="v">0</div></div>
        <div class="card"><div class="k">AOIs</div><div id="cardAois" class="v">0</div></div>
      </div>
      <div class="cards-groups">
        <div class="group pre">
          <div class="group-title">Metricas pre-atentivas</div>
          <div class="cards-grid">
            <div class="card"><div class="k">FB media</div><div id="cardFb" class="v">-1</div></div>
            <div class="card"><div class="k">TFF media (ms)</div><div id="cardTff" class="v">-1</div></div>
          </div>
        </div>
        <div class="group sustained">
          <div class="group-title">Metricas sostenidas</div>
          <div class="cards-grid wide">
            <div class="card"><div class="k">FD media (ms)</div><div id="cardFd" class="v">-1</div></div>
            <div class="card"><div class="k">TFD media (ms)</div><div id="cardTfd" class="v">-1</div></div>
            <div class="card"><div class="k">FC media</div><div id="cardFc" class="v">-1</div></div>
            <div class="card"><div class="k">Visitas medias</div><div id="cardVisits" class="v">-1</div></div>
            <div class="card"><div class="k">AOIs con revisitas</div><div id="cardRevisits" class="v">0</div></div>
          </div>
        </div>
      </div>
    </section>

    <section class="table-panel">
      <div class="toolbar">
        <div class="note">La tabla muestra todas las filas del CSV AOI resumido. Si una AOI no fue visitada en la fila filtrada, sus metricas se exportan como <strong>-1</strong>.</div>
        <div class="note" id="toolbarNote"></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr class="group-row">
              <th rowspan="2">Participante</th>
              <th rowspan="2">Estimulo</th>
              <th rowspan="2">AOI</th>
              <th rowspan="2">Categoria</th>
              <th colspan="2" class="pre-head">Pre-atentivas</th>
              <th colspan="5" class="sustained-head">Sostenidas</th>
            </tr>
            <tr>
              <th>FB</th>
              <th>TFF (ms)</th>
              <th>FD (ms)</th>
              <th>TFD (ms)</th>
              <th>FC</th>
              <th>Visits</th>
              <th>Revisitas</th>
            </tr>
          </thead>
          <tbody id="tableBody"></tbody>
        </table>
      </div>
      <div id="emptyState" class="empty" hidden>No hay filas que coincidan con los filtros actuales.</div>
    </section>
  </div>

  <script>
    const dataset = {dataset_json};
    const participantFilter = document.getElementById("participantFilter");
    const videoFilter = document.getElementById("videoFilter");
    const aoiFilter = document.getElementById("aoiFilter");
    const searchFilter = document.getElementById("searchFilter");
    const tableBody = document.getElementById("tableBody");
    const emptyState = document.getElementById("emptyState");
    const toolbarNote = document.getElementById("toolbarNote");

    function uniqueValues(key) {{
      return [...new Set(dataset.map(row => row[key]).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b)));
    }}

    function fillSelect(select, values, allLabel) {{
      select.innerHTML = "";
      const allOption = document.createElement("option");
      allOption.value = "";
      allOption.textContent = allLabel;
      select.appendChild(allOption);
      values.forEach(value => {{
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      }});
    }}

    function formatMetric(value, digits = 2) {{
      if (value < 0) {{
        return "-1";
      }}
      return Number(value).toLocaleString("es-ES", {{
        minimumFractionDigits: digits,
        maximumFractionDigits: digits
      }});
    }}

    function metricMean(rows, key) {{
      const validValues = rows
        .map(row => Number(row[key]))
        .filter(value => Number.isFinite(value) && value >= 0);
      if (!validValues.length) {{
        return -1;
      }}
      return validValues.reduce((sum, value) => sum + value, 0) / validValues.length;
    }}

    function filterRows() {{
      const participant = participantFilter.value;
      const video = videoFilter.value;
      const aoi = aoiFilter.value;
      const search = searchFilter.value.trim().toLowerCase();

      return dataset.filter(row => {{
        if (participant && row.participant_id !== participant) return false;
        if (video && row.video_id !== video) return false;
        if (aoi && row.aoi_name !== aoi) return false;
        if (search) {{
          const haystack = [
            row.participant_id,
            row.video_id,
            row.aoi_name,
            row.aoi_category,
            row.aoi_prompt
          ].join(" ").toLowerCase();
          if (!haystack.includes(search)) return false;
        }}
        return true;
      }});
    }}

    function refreshAoiOptions() {{
      const participant = participantFilter.value;
      const video = videoFilter.value;
      const currentAoi = aoiFilter.value;

      const candidateRows = dataset.filter(row => {{
        if (participant && row.participant_id !== participant) return false;
        if (video && row.video_id !== video) return false;
        return true;
      }});

      const aoiValues = [...new Set(candidateRows.map(row => row.aoi_name).filter(Boolean))]
        .sort((a, b) => String(a).localeCompare(String(b)));

      fillSelect(aoiFilter, aoiValues, "Todas las AOI");
      if (currentAoi && aoiValues.includes(currentAoi)) {{
        aoiFilter.value = currentAoi;
      }}
    }}

    function updateCards(rows) {{
      document.getElementById("cardRows").textContent = rows.length;
      document.getElementById("cardParticipants").textContent = new Set(rows.map(row => row.participant_id)).size;
      document.getElementById("cardVideos").textContent = new Set(rows.map(row => row.video_id)).size;
      document.getElementById("cardAois").textContent = new Set(rows.map(row => `${{row.video_id}}|${{row.aoi_name}}`)).size;
      document.getElementById("cardFb").textContent = formatMetric(metricMean(rows, "fb_count"), 2);
      document.getElementById("cardTff").textContent = formatMetric(metricMean(rows, "tff_ms"), 1);
      document.getElementById("cardFd").textContent = formatMetric(metricMean(rows, "fd_ms"), 1);
      document.getElementById("cardTfd").textContent = formatMetric(metricMean(rows, "tfd_ms"), 1);
      document.getElementById("cardFc").textContent = formatMetric(metricMean(rows, "fc"), 2);
      document.getElementById("cardVisits").textContent = formatMetric(metricMean(rows, "visit_count"), 2);
      document.getElementById("cardRevisits").textContent = rows.filter(row => row.has_revisits === 1).length;
      toolbarNote.textContent = `Mostrando ${{rows.length}} fila(s) filtradas de ${{dataset.length}} totales.`;
    }}

    function renderMetricCell(value, digits = 2) {{
      const formatted = formatMetric(Number(value), digits);
      const cls = Number(value) < 0 ? "neg" : "";
      return `<span class="${{cls}}">${{formatted}}</span>`;
    }}

    function renderRows(rows) {{
      tableBody.innerHTML = "";
      if (!rows.length) {{
        emptyState.hidden = false;
        return;
      }}
      emptyState.hidden = true;

      rows.forEach(row => {{
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><code>${{row.participant_id}}</code></td>
          <td><code>${{row.video_id}}</code></td>
          <td>
            <span class="pill">
              <span class="dot" style="background:${{row.aoi_color || '#cccccc'}}"></span>
              <code>${{row.aoi_name}}</code>
            </span>
          </td>
          <td>${{row.aoi_category || ''}}</td>
          <td>${{renderMetricCell(row.fb_count, 0)}}</td>
          <td>${{renderMetricCell(row.tff_ms, 1)}}</td>
          <td>${{renderMetricCell(row.fd_ms, 1)}}</td>
          <td>${{renderMetricCell(row.tfd_ms, 1)}}</td>
          <td>${{renderMetricCell(row.fc, 0)}}</td>
          <td>${{renderMetricCell(row.visit_count, 0)}}</td>
          <td class="checkbox-cell"><input type="checkbox" disabled ${{row.has_revisits === 1 ? "checked" : ""}}></td>
        `;
        tableBody.appendChild(tr);
      }});

      const summaryRow = document.createElement("tr");
      summaryRow.className = "summary-row";
      summaryRow.innerHTML = `
        <td colspan="4"><strong>Media visible</strong></td>
        <td>${{formatMetric(metricMean(rows, "fb_count"), 2)}}</td>
        <td>${{formatMetric(metricMean(rows, "tff_ms"), 1)}}</td>
        <td>${{formatMetric(metricMean(rows, "fd_ms"), 1)}}</td>
        <td>${{formatMetric(metricMean(rows, "tfd_ms"), 1)}}</td>
        <td>${{formatMetric(metricMean(rows, "fc"), 2)}}</td>
        <td>${{formatMetric(metricMean(rows, "visit_count"), 2)}}</td>
        <td class="checkbox-cell"><input type="checkbox" disabled ${{rows.some(row => row.has_revisits === 1) ? "checked" : ""}}></td>
      `;
      tableBody.appendChild(summaryRow);
    }}

    function refresh() {{
      const rows = filterRows();
      updateCards(rows);
      renderRows(rows);
    }}

    fillSelect(participantFilter, uniqueValues("participant_id"), "Todos los participantes");
    fillSelect(videoFilter, uniqueValues("video_id"), "Todos los estimulos");
    refreshAoiOptions();

    participantFilter.addEventListener("change", () => {{
      refreshAoiOptions();
      refresh();
    }});
    videoFilter.addEventListener("change", () => {{
      refreshAoiOptions();
      refresh();
    }});
    aoiFilter.addEventListener("change", refresh);
    searchFilter.addEventListener("input", refresh);
    refresh();
  </script>
</body>
</html>
"""


def build_runtime_aoi_html_report(*, input_csv: Path, output_html: Path, title: str) -> None:
    rows = _read_rows(input_csv)
    html_text = _build_html(title=title, rows=rows, source_csv=input_csv.name)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html_text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a static HTML explorer for runtime_aoi_summary.csv exports.",
    )
    parser.add_argument("--input-csv", required=True, help="Path to runtime_aoi_summary.csv")
    parser.add_argument("--output-html", help="Destination HTML path")
    parser.add_argument(
        "--title",
        default="AOI360 Phase 3 AOI Explorer",
        help="HTML report title",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_csv = Path(args.input_csv).resolve()
    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    output_html = (
        Path(args.output_html).resolve()
        if args.output_html
        else input_csv.with_name(f"{input_csv.stem}_viewer.html")
    )
    build_runtime_aoi_html_report(
        input_csv=input_csv,
        output_html=output_html,
        title=args.title,
    )
    print(output_html)


if __name__ == "__main__":
    main()
