from io import BytesIO

import pandas as pd

from services.grade_report_service import attach_scholarships, build_excel, build_report_tables, load_scholarships


def test_scholarship_match_and_unknown():
    data = BytesIO(b'Correo,Tipo de beca\na@uvg.edu.gt,Academica\n')
    data.name = 'becas.csv'
    scholarship_df = load_scholarships(data)
    records = pd.DataFrame([
        {'email': 'A@UVG.EDU.GT', 'carne': '123'},
        {'email': 'b@uvg.edu.gt', 'carne': '124'},
    ])
    out = attach_scholarships(records, scholarship_df)
    assert out.loc[0, 'tiene_beca'] == 'Sí'
    assert out.loc[0, 'tipo_beca'] == 'Academica'
    assert out.loc[1, 'tiene_beca'] == 'Por verificar'


def test_negative_scholarship_and_conflicting_records():
    df = pd.DataFrame([
        {'correo': 'a@uvg.edu.gt', 'carne': '11', 'becado': 'No', 'tipo_beca': ''},
        {'correo': 'b@uvg.edu.gt', 'carne': '22', 'becado': 'Si', 'tipo_beca': 'Parcial'},
    ])
    for col in ('correo', 'carne'):
        df[f'{col}_key'] = df[col]
    result = attach_scholarships(pd.DataFrame([
        {'email': 'a@uvg.edu.gt', 'carne': '11'},
        {'email': 'a@uvg.edu.gt', 'carne': '22'},
    ]), df)
    assert result.loc[0, 'tiene_beca'] == 'No'
    assert result.loc[1, 'tiene_beca'] == 'Por verificar'
    assert result.loc[1, 'coincidencia_beca'] == 'Conflicto correo/carné'


def test_export_multiple_courses_with_activity_details():
    snapshots = {}
    for cid in ['1', '2']:
        snapshots[cid] = {
            'dataframe': pd.DataFrame([{
                'canvas_user_id': '10', 'student_name': 'Alumno', 'email': 'a@uvg.edu.gt',
                'carne': '11', 'asesor_bienestar': 'Bienestar', 'course_id': cid,
                'course_name': f'Curso {cid}', 'section_name': 'A', 'average_grade': 85,
            }]),
            'details': {'10': {'assignments': [{'actividad': 'Tarea', 'puntaje': 8,
                'puntos_posibles': 10, 'completada': True}]}}
        }
    summary, detail, pending = build_report_tables(snapshots, ['1', '2'], None)
    assert len(summary) == 2
    assert len(detail) == 2
    assert len(pending) == 2
    excel = build_excel(summary, detail, pending)
    assert excel[:2] == b'PK'
    assert pd.read_excel(BytesIO(excel), sheet_name='Resumen de calificaciones').shape[0] == 2


def test_real_cohort_style_multisheet_and_header_offset():
    from services.grade_report_service import combine_scholarships
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame([
            [None, None, None, None],
            ["Carné", "Nombre", "Beca", "Correo UVG "],
            ["1001", "Estudiante A", "DESPEGA", "a@uvg.edu.gt"],
        ]).to_excel(writer, sheet_name="Cohorte", header=False, index=False)
        pd.DataFrame([
            [None, None, None, None, None],
            [None, "Carné", "Nombre", "Beca", "Correo UVG "],
            [None, "1002", "Estudiante B", "TRANSFORMA", "b@uvg.edu.gt"],
        ]).to_excel(writer, sheet_name="Casos particulares", header=False, index=False)
    buf.seek(0)
    buf.name = "becas.xlsx"
    result = combine_scholarships([buf])
    assert len(result) == 2
    assert set(result["tipo_beca"]) == {"DESPEGA", "TRANSFORMA"}
    assert set(result["correo_key"]) == {"a@uvg.edu.gt", "b@uvg.edu.gt"}
    assert not any(col.lower() in {"dpi", "fecha nacimiento"} for col in result.columns)
