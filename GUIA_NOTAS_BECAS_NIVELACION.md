# Módulo de notas y becas — Nivelación AVE

Esta versión se basa exclusivamente en `ALERTA-TEMPRANA-LTI-NIVELACION--main (4).zip`. No sustituya con archivos de la otra aplicación de asesores académicos.

## Uso

1. Inicie sesión con una cuenta con permiso de Configuración.
2. En **Configuración → Supabase y bienestar**, cargue los dos archivos Excel de becas de las cohortes. No los agregue al repositorio.
3. Entre a **Conexión y análisis**, ejecute un corte por cada curso o sección que desea integrar. La aplicación conserva el último corte de cada combinación curso/sección durante la sesión.
4. Abra **Dashboard general → Reporte general de calificaciones y becas**, marque los cursos y secciones y descargue el Excel.

## Contenido del Excel

- **Resumen de calificaciones**: una fila por inscripción de alumno en curso, nota porcentual actual calculada/recuperada por el análisis original, avance, asesor, beca.
- **Detalle por actividad**: puntajes y estado de entrega del corte ejecutado.
- **Becas por verificar**: alumnos sin coincidencia confirmada o con coincidencias contradictorias. La ausencia del listado no se interpreta como No becado.

## Límites importantes

- **No hay persistencia institucional de los listados**: el catálogo y los cortes acumulados están solo en la sesión de Streamlit, y se pierden al reiniciar o cerrar la sesión.
- **No se consultan calificaciones de cursos sin analizar**: hay que ejecutar su corte durante la sesión. La nota es la nota disponible al momento del corte, y no necesariamente la final.
- **Mismo curso con secciones solapadas**: si se analiza Todas las secciones y luego una sección específica, seleccione solo una de esas vistas para evitar duplicados.
- **Privacidad**: no publicar las bases de becados ni exportaciones con información personal en GitHub. Descargas solo para personal institucional autorizado; verificar permisos vigentes antes de usar en producción.
- **Reversión**: un commit previo en GitHub permite revertir si se identifican fallos tras desplegar.

## Archivos modificados

`pages/inicio.py`, `pages/configuracion.py`, `pages/dashboard_general.py`.

## Archivos agregados

`services/grade_report_service.py`, `tests/test_grade_report.py`, esta guía.

No se alteró la lógica de riesgo, derivaciones, Canvas, Supabase, ni dependencias.
