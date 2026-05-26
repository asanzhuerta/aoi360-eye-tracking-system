from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path


def _read_rows(csv_path: Path) -> list[dict[str, object]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, object]] = []
        for raw_row in reader:
            fixation_steps = int(float(raw_row["fixation_steps"]))
            dwell_time_ms = float(raw_row["dwell_time_ms"])
            time_to_first_fixation_ms = float(raw_row["time_to_first_fixation_ms"])
            visit_count = int(float(raw_row["visit_count"]))
            mean_confidence = float(raw_row["mean_aoi_confidence"])
            dwell_share_valid = float(raw_row["dwell_share_of_valid_time"])
            dwell_share_assigned = float(raw_row["dwell_share_of_assigned_time"])
            fixation_step_ms_estimate = float(raw_row["fixation_step_ms_estimate"])

            rows.append(
                {
                    "participant_id": raw_row["participant_id"],
                    "session_id": raw_row["session_id"],
                    "video_id": raw_row["video_id"],
                    "aoi_id": int(float(raw_row["aoi_id"])),
                    "aoi_name": raw_row.get("aoi_name", ""),
                    "aoi_category": raw_row.get("aoi_category", ""),
                    "aoi_prompt": raw_row.get("aoi_prompt", ""),
                    "aoi_color": raw_row.get("aoi_color", ""),
                    "fixation_steps": fixation_steps,
                    "visit_count": visit_count,
                    "dwell_time_ms": dwell_time_ms,
                    "dwell_time_s": round(dwell_time_ms / 1000.0, 3),
                    "time_to_first_fixation_ms": time_to_first_fixation_ms,
                    "time_to_first_fixation_s": round(time_to_first_fixation_ms / 1000.0, 3),
                    "fd_ms": round((dwell_time_ms / fixation_steps), 3) if fixation_steps else 0.0,
                    "mean_aoi_confidence": round(mean_confidence, 4),
                    "dwell_share_of_valid_time": round(dwell_share_valid, 4),
                    "dwell_share_of_assigned_time": round(dwell_share_assigned, 4),
                    "fixation_step_ms_estimate": round(fixation_step_ms_estimate, 3),
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
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      background: linear-gradient(180deg, #f7f3eb 0%, #f1ece1 100%);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 28px 24px 40px;
    }}
    .hero {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 24px;
      box-shadow: 0 12px 30px rgba(39, 32, 18, 0.06);
      margin-bottom: 20px;
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
    .filters, .cards, .table-panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 12px 30px rgba(39, 32, 18, 0.05);
      margin-bottom: 18px;
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
    .cards-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      background: linear-gradient(180deg, #fffefb 0%, #faf6ee 100%);
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
      font-size: 26px;
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
      min-width: 1180px;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid #ebe3d6;
      text-align: left;
      font-size: 13px;
      white-space: nowrap;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #fcf7ef;
      z-index: 1;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
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
    @media (max-width: 1080px) {{
      .filters-grid, .cards-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 640px) {{
      .wrap {{ padding: 18px 14px 28px; }}
      .filters-grid, .cards-grid {{
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
      <p class="subtitle">Visor HTML de Phase 3 generado desde <code>{source_csv_escaped}</code>. Filtra por participante, estímulo y AOI para inspeccionar TFF, FD, TFD, FC y visitas.</p>
    </section>

    <section class="filters">
      <div class="filters-grid">
        <div>
          <label for="participantFilter">Participante</label>
          <select id="participantFilter"></select>
        </div>
        <div>
          <label for="videoFilter">Estímulo</label>
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
      <div class="cards-grid">
        <div class="card"><div class="k">Filas visibles</div><div id="cardRows" class="v">0</div></div>
        <div class="card"><div class="k">Participantes</div><div id="cardParticipants" class="v">0</div></div>
        <div class="card"><div class="k">Estímulos</div><div id="cardVideos" class="v">0</div></div>
        <div class="card"><div class="k">AOIs</div><div id="cardAois" class="v">0</div></div>
        <div class="card"><div class="k">TFD total (s)</div><div id="cardTfd" class="v">0</div></div>
        <div class="card"><div class="k">Visitas totales</div><div id="cardVisits" class="v">0</div></div>
      </div>
    </section>

    <section class="table-panel">
      <div class="toolbar">
        <div class="note">La tabla muestra todas las filas del CSV AOI resumido. Las columnas derivadas <strong>FD</strong>, <strong>TFF</strong> y <strong>TFD</strong> se calculan a partir del propio export de Phase 3.</div>
        <div class="note" id="toolbarNote"></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Participante</th>
              <th>Estímulo</th>
              <th>AOI</th>
              <th>Categoría</th>
              <th>FC</th>
              <th>FD (ms)</th>
              <th>TFD (s)</th>
              <th>TFF (s)</th>
              <th>Visitas</th>
              <th>Dwell valid</th>
              <th>Dwell assigned</th>
              <th>Conf.</th>
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

    const formatNumber = (value, digits = 2) => Number(value).toLocaleString("es-ES", {{
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    }});

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
      document.getElementById("cardTfd").textContent = formatNumber(rows.reduce((sum, row) => sum + row.dwell_time_s, 0), 2);
      document.getElementById("cardVisits").textContent = rows.reduce((sum, row) => sum + row.visit_count, 0);
      toolbarNote.textContent = `Mostrando ${{rows.length}} fila(s) filtradas de ${{dataset.length}} totales.`;
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
          <td>${{row.fixation_steps}}</td>
          <td>${{formatNumber(row.fd_ms, 1)}}</td>
          <td>${{formatNumber(row.dwell_time_s, 2)}}</td>
          <td>${{formatNumber(row.time_to_first_fixation_s, 2)}}</td>
          <td>${{row.visit_count}}</td>
          <td>${{formatNumber(row.dwell_share_of_valid_time * 100, 1)}}%</td>
          <td>${{formatNumber(row.dwell_share_of_assigned_time * 100, 1)}}%</td>
          <td>${{formatNumber(row.mean_aoi_confidence, 3)}}</td>
        `;
        tableBody.appendChild(tr);
      }});

      const mean = (selector) => rows.length ? rows.reduce((sum, row) => sum + selector(row), 0) / rows.length : 0;
      const summaryRow = document.createElement("tr");
      summaryRow.className = "summary-row";
      summaryRow.innerHTML = `
        <td colspan="4"><strong>Media visible</strong></td>
        <td>${{formatNumber(mean(row => row.fixation_steps), 2)}}</td>
        <td>${{formatNumber(mean(row => row.fd_ms), 1)}}</td>
        <td>${{formatNumber(mean(row => row.dwell_time_s), 2)}}</td>
        <td>${{formatNumber(mean(row => row.time_to_first_fixation_s), 2)}}</td>
        <td>${{formatNumber(mean(row => row.visit_count), 2)}}</td>
        <td>${{formatNumber(mean(row => row.dwell_share_of_valid_time) * 100, 1)}}%</td>
        <td>${{formatNumber(mean(row => row.dwell_share_of_assigned_time) * 100, 1)}}%</td>
        <td>${{formatNumber(mean(row => row.mean_aoi_confidence), 3)}}</td>
      `;
      tableBody.appendChild(summaryRow);
    }}

    function refresh() {{
      const rows = filterRows();
      updateCards(rows);
      renderRows(rows);
    }}

    fillSelect(participantFilter, uniqueValues("participant_id"), "Todos los participantes");
    fillSelect(videoFilter, uniqueValues("video_id"), "Todos los estímulos");
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
