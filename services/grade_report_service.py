"""Reporte académico multcurso: becas por identificador y exportación Excel."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import unicodedata

import pandas as pd


def _normalized(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower()


def _column_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", text)


ALIASES = {
    "correo": {"correo", "correoinstitucional", "correouv g", "correouv g ", "correouv g", "correouv g", "correouv g", "correouv g", "correo uv g", "correo uvg", "correouvg", "email", "mail", "e-mail"},
    "carne": {"carne", "carnet", "no carné", "numerodecarne", "id estudiante", "studentid", "sisuserid"},
    "tipo_beca": {"tipobeca", "tipodebeca", "beca", "nombrebeca", "programadebeca"},
    "becado": {"becado", "esbecado", "tienebeca", "estadobeca", "estatusbeca"},
}


def _extract_scholarship_sheet(raw: pd.DataFrame) -> pd.DataFrame:
    """Ubica encabezados en filas iniciales; evita importar columnas sensibles."""
    found = None
    for header_pos in range(min(12, len(raw))):
        row = list(raw.iloc[header_pos])
        positions = {}
        for field, aliases in ALIASES.items():
            aliases_norm = {_column_key(alias) for alias in aliases}
            for idx, value in enumerate(row):
                if _column_key(value) in aliases_norm:
                    positions[field] = idx
                    break
        if ({"correo", "carne"} & positions.keys()) and ({"tipo_beca", "becado"} & positions.keys()):
            found = (header_pos, positions)
            break
    if found is None:
        return pd.DataFrame()
    header_pos, positions = found
    body = raw.iloc[header_pos + 1:].copy()
    result = pd.DataFrame({field: body.iloc[:, idx].fillna("").astype(str).str.strip() for field, idx in positions.items()})
    for field in ("correo", "carne", "tipo_beca", "becado"):
        if field not in result:
            result[field] = ""
    result["correo_key"] = result["correo"].map(_normalized)
    result["carne_key"] = result["carne"].map(lambda x: re.sub(r"\s+", "", _normalized(x)).removesuffix(".0"))
    result = result[(result["correo_key"] != "") | (result["carne_key"] != "")].copy()
    return result.reset_index(drop=True)


def load_scholarships(source) -> pd.DataFrame:
    """Acepta archivos institucionales de ambas cohortes y todas las hojas útiles."""
    name = str(getattr(source, "name", source)).lower()
    if hasattr(source, "seek"):
        source.seek(0)
    if name.endswith(".xlsx"):
        raw_sheets = pd.read_excel(source, sheet_name=None, header=None, dtype=str)
    else:
        try:
            raw = pd.read_csv(source, header=None, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
        except UnicodeDecodeError:
            if hasattr(source, "seek"):
                source.seek(0)
            raw = pd.read_csv(source, header=None, dtype=str, sep=None, engine="python", encoding="latin1")
        raw_sheets = {"CSV": raw}
    extracted = [_extract_scholarship_sheet(raw) for raw in raw_sheets.values()]
    extracted = [frame for frame in extracted if not frame.empty]
    if not extracted:
        raise ValueError("No se localizaron encabezados válidos (Carné o Correo UVG, y Beca).")
    result = pd.concat(extracted, ignore_index=True)
    # Casos particulares pueden repetir alumnos de la hoja principal.
    # Se consolidan únicamente registros idénticos para evitar duplicados falsos.
    result = result.drop_duplicates(subset=["correo_key", "carne_key", "tipo_beca", "becado"]).reset_index(drop=True)
    return result


def combine_scholarships(sources) -> pd.DataFrame:
    """Integra varios archivos/cohortes; conserva diferencias para validación."""
    frames = [load_scholarships(source) for source in sources]
    if not frames:
        raise ValueError("Debe seleccionar al menos un archivo.")
    return pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["correo_key", "carne_key", "tipo_beca", "becado"]
    ).reset_index(drop=True)


def _status(row: pd.Series) -> tuple[str, str]:
    value = _normalized(row.get("becado"))
    kind = str(row.get("tipo_beca") or "").strip()
    no_values = {"no", "n", "false", "0", "sin beca", "no aplica"}
    yes_values = {"si", "sí", "s", "true", "1", "becado"}
    if value in no_values:
        return "No", "No aplica"
    if value in yes_values or (kind and _normalized(kind) not in no_values | {"no aplica", "ninguna"}):
        return "Sí", kind or "Tipo no indicado"
    return "Por verificar", "Por verificar"


def attach_scholarships(analysis: pd.DataFrame, scholarship_df: pd.DataFrame | None) -> pd.DataFrame:
    """No asume que ausencia en listado sea equivalente a ausencia de beca."""
    out = analysis.copy()
    out["tiene_beca"] = "Por verificar"
    out["tipo_beca"] = "Por verificar"
    out["coincidencia_beca"] = "Sin listado"
    if scholarship_df is None or scholarship_df.empty or out.empty:
        return out

    emails, carnes = {}, {}
    for index, item in scholarship_df.iterrows():
        if item["correo_key"]:
            emails.setdefault(item["correo_key"], []).append(index)
        if item["carne_key"]:
            carnes.setdefault(item["carne_key"], []).append(index)
    for idx, student in out.iterrows():
        email = _normalized(student.get("email"))
        carne = re.sub(r"\s+", "", _normalized(student.get("carne")))
        by_email = emails.get(email, []) if email else []
        by_carne = carnes.get(carne, []) if carne and not carne.startswith("canvas-") else []
        if by_email and by_carne and set(by_email) != set(by_carne):
            out.at[idx, "coincidencia_beca"] = "Conflicto correo/carné"
            continue
        matches = set(by_email or by_carne)
        if len(matches) != 1:
            out.at[idx, "coincidencia_beca"] = "Coincidencia duplicada" if matches else "No figura en listado"
            continue
        row = scholarship_df.loc[next(iter(matches))]
        status, kind = _status(row)
        out.at[idx, "tiene_beca"] = status
        out.at[idx, "tipo_beca"] = kind
        out.at[idx, "coincidencia_beca"] = "Correo" if by_email else "Carné"
    return out


SUMMARY_COLUMNS = {
    "student_name": "Nombre completo", "carne": "Carné", "email": "Correo institucional",
    "asesor_bienestar": "Asesor de bienestar", "tiene_beca": "¿Tiene beca?",
    "tipo_beca": "Tipo de beca", "coincidencia_beca": "Validación de beca",
    "course_name": "Curso", "section_name": "Sección", "average_grade": "Nota actual (%)",
    "completion_percentage": "Avance de actividades (%)", "completed_expected": "Actividades esperadas completadas",
    "expected_activities": "Actividades esperadas", "pending_count": "Actividades pendientes",
    "overall_risk": "Riesgo general", "week_number": "Semana del análisis",
    "analysis_cutoff": "Fecha del corte", "course_id": "ID del curso",
}


def build_report_tables(course_snapshots: dict, selected_keys: list[str], scholarships: pd.DataFrame | None):
    summaries, activity_rows = [], []
    for key in selected_keys:
        snapshot = course_snapshots[key]
        df = snapshot["dataframe"].copy()
        if df.empty:
            continue
        df = attach_scholarships(df, scholarships)
        summaries.append(df)
        for _, student in df.iterrows():
            detail = snapshot.get("details", {}).get(str(student.get("canvas_user_id")), {})
            for activity in detail.get("assignments", []):
                activity_rows.append({
                    "Nombre completo": student.get("student_name", ""),
                    "Carné": student.get("carne", ""),
                    "Correo institucional": student.get("email", ""),
                    "Asesor de bienestar": student.get("asesor_bienestar", "Sin asignar"),
                    "¿Tiene beca?": student.get("tiene_beca", "Por verificar"),
                    "Tipo de beca": student.get("tipo_beca", "Por verificar"),
                    "Curso": student.get("course_name", ""),
                    "Sección": student.get("section_name", ""),
                    "Actividad": activity.get("actividad"),
                    "Puntos obtenidos": activity.get("puntaje"),
                    "Puntos posibles": activity.get("puntos_posibles"),
                    "Entregada": "Sí" if activity.get("completada") else "No",
                    "Esperada al corte": "Sí" if activity.get("esperada_a_la_fecha") else "No",
                    "Fecha límite": activity.get("fecha_limite"),
                    "Fecha de entrega": activity.get("fecha_entrega"),
                })
    if not summaries:
        raise ValueError("No hay análisis con estudiantes para exportar.")
    combined = pd.concat(summaries, ignore_index=True)
    # No duplicar estudiantes por combinaciones de análisis de la misma sección/curso.
    combined = combined.drop_duplicates(subset=["course_id", "canvas_user_id"], keep="last")
    summary = combined.reindex(columns=list(SUMMARY_COLUMNS)).rename(columns=SUMMARY_COLUMNS)
    detail = pd.DataFrame(activity_rows)
    pending = summary[summary["¿Tiene beca?"] == "Por verificar"].copy()
    return summary, detail, pending


def build_excel(summary: pd.DataFrame, detail: pd.DataFrame, pending: pd.DataFrame) -> bytes:
    """Devuelve XLSX con filtros, cabeceras y formatos apropiados, sin fórmulas ejecutables."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, frame in (
            ("Resumen de calificaciones", summary),
            ("Detalle por actividad", detail),
            ("Becas por verificar", pending),
        ):
            safe = frame.fillna("").copy()
            for col in safe.select_dtypes(include=["object", "string"]).columns:
                safe[col] = safe[col].map(lambda x: "'" + x if isinstance(x, str) and x.startswith(("=", "+", "-", "@")) else x)
            safe.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            from openpyxl.styles import Font, PatternFill, Alignment
            for cell in ws[1]:
                cell.fill = PatternFill("solid", fgColor="163B63")
                cell.font = Font(bold=True, color="FFFFFF")
                cell.alignment = Alignment(wrap_text=True, vertical="center")
            ws.row_dimensions[1].height = 34
            for col in ws.columns:
                letter = col[0].column_letter
                longest = max((len(str(c.value or "")) for c in list(col)[:200]), default=12)
                ws.column_dimensions[letter].width = min(45, max(14, longest + 2))
    return output.getvalue()
