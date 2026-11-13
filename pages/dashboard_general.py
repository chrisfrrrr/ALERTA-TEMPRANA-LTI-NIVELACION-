from __future__ import annotations

import pandas as pd
import streamlit as st

from components.charts import advisor_workload, progress_by_student, risk_distribution, top_risk_causes
from components.ui import dataframe_for_display, empty_state, metric_card, page_header
from services.grade_report_service import build_excel, build_report_tables


page_header(
    "Dashboard general",
    "Vista ejecutiva del riesgo académico, causas principales, evolución y carga de seguimiento por asesor de bienestar.",
)

df = st.session_state.get("analysis_df")
if df is None or df.empty:
    empty_state("Aún no existe un análisis", "Ejecute primero un corte semanal desde la página Conexión y análisis.")
    st.stop()

filter1, filter2, filter3, filter4 = st.columns([1.2, 1.6, 1.6, 2.1])
with filter1:
    risks = st.multiselect("Riesgo", ["Bajo", "Moderado", "Alto", "Sin datos"], default=["Bajo", "Moderado", "Alto"])
with filter2:
    advisors = sorted(df.get("asesor_bienestar", pd.Series(dtype=str)).fillna("Sin asignar").unique().tolist())
    selected_advisors = st.multiselect("Asesor de bienestar", advisors, default=advisors)
with filter3:
    evolutions = sorted(df["evolution"].fillna("Sin dato").unique().tolist())
    selected_evolutions = st.multiselect("Evolución", evolutions, default=evolutions)
with filter4:
    search = st.text_input("Buscar por nombre, carné o correo", placeholder="Ejemplo: 262597 o Alicia")

filtered = df.copy()
if risks:
    filtered = filtered[filtered["overall_risk"].isin(risks)]
if "asesor_bienestar" in filtered.columns and selected_advisors:
    filtered = filtered[filtered["asesor_bienestar"].fillna("Sin asignar").isin(selected_advisors)]
if selected_evolutions:
    filtered = filtered[filtered["evolution"].isin(selected_evolutions)]
if search:
    needle = search.lower().strip()
    mask = (
        filtered["student_name"].astype(str).str.lower().str.contains(needle, na=False)
        | filtered["carne"].astype(str).str.lower().str.contains(needle, na=False)
        | filtered["email"].astype(str).str.lower().str.contains(needle, na=False)
    )
    filtered = filtered[mask]

if filtered.empty:
    empty_state("No hay resultados", "Ajuste los filtros para volver a mostrar estudiantes.")
    st.stop()

m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    metric_card("Analizados", len(filtered), f"de {len(df)} en el corte")
with m2:
    metric_card("Riesgo bajo", int((filtered["overall_risk"] == "Bajo").sum()), "Seguimiento preventivo")
with m3:
    metric_card("Riesgo moderado", int((filtered["overall_risk"] == "Moderado").sum()), "Contacto y posible derivación")
with m4:
    metric_card("Riesgo alto", int((filtered["overall_risk"] == "Alto").sum()), "Atención prioritaria")
with m5:
    metric_card("Mejorando", int((filtered["evolution"] == "Mejorando").sum()), "Respecto del corte anterior")

chart1, chart2 = st.columns([1, 1.35])
with chart1:
    st.subheader("Distribución del riesgo")
    st.plotly_chart(risk_distribution(filtered), width="stretch")
with chart2:
    st.subheader("Indicadores que generan más alertas")
    st.plotly_chart(top_risk_causes(filtered), width="stretch")

chart3, chart4 = st.columns([1.25, 1])
with chart3:
    st.subheader("Estudiantes con mayor brecha de avance")
    st.plotly_chart(progress_by_student(filtered), width="stretch")
with chart4:
    st.subheader("Casos por asesor de bienestar")
    if filtered["overall_risk"].isin(["Moderado", "Alto"]).any():
        st.plotly_chart(advisor_workload(filtered), width="stretch")
    else:
        st.info("No existen casos moderados o altos en el filtro actual.")

st.subheader("Listado operativo")
show = dataframe_for_display(filtered)
st.dataframe(show, width="stretch", hide_index=True, height=430)

csv = filtered.to_csv(index=False).encode("utf-8-sig")
action1, action2, action3 = st.columns([1.1, 1.3, 2.2])
with action1:
    st.download_button("Descargar CSV", data=csv, file_name="analisis_semanal_ave.csv", mime="text/csv", width="stretch")
with action2:
    student_options = {
        f"{row.student_name} · {row.carne}": row.canvas_user_id for row in filtered.itertuples()
    }
    selected_label = st.selectbox("Abrir expediente", list(student_options.keys()), label_visibility="collapsed") if student_options else None
with action3:
    if selected_label and st.button("Ver dashboard individual", type="primary", width="stretch"):
        st.session_state.selected_student_id = str(student_options[selected_label])
        st.switch_page("pages/estudiante.py")


st.divider()
st.subheader("Reporte general de calificaciones y becas")
st.caption(
    "Incluye los últimos cortes realizados durante esta sesión para los cursos y secciones elegidos. "
    "La nota corresponde a la calificación actual registrada en el corte, no necesariamente a la nota final. "
    "Cargue los listados de becas desde Configuración."
)
snapshots = st.session_state.get("course_report_snapshots", {})
mode = "demo" if st.session_state.get("demo_mode") else "canvas"
available_keys = [key for key, snap in snapshots.items() if snap.get("mode") == mode]
if available_keys:
    selected_keys = st.multiselect(
        "Cursos y secciones a incluir en el Excel",
        options=available_keys,
        default=available_keys,
        format_func=lambda key: snapshots[key]["label"],
        key="lti_grade_report_courses",
    )
    if selected_keys:
        try:
            summary, activities, pending = build_report_tables(
                snapshots, selected_keys, st.session_state.get("scholarships_df")
            )
            a, b, c = st.columns(3)
            a.metric("Inscripciones", len(summary))
            b.metric("Cursos", summary["ID del curso"].nunique())
            c.metric("Becas por verificar", len(pending))
            if st.session_state.get("scholarships_df") is None:
                st.warning("No hay catálogo de becas cargado; los estados se mostrarán como Por verificar.")
            st.dataframe(summary, width="stretch", hide_index=True, height=300)
            st.download_button(
                "Descargar Excel general de notas y becas",
                data=build_excel(summary, activities, pending),
                file_name="AVE_nivelacion_notas_becas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary", width="stretch",
            )
        except (ValueError, KeyError) as exc:
            st.error(f"No fue posible preparar el Excel: {exc}")
else:
    st.info("Ejecute el análisis de uno o más cursos desde Conexión y análisis para habilitar este descargable.")
