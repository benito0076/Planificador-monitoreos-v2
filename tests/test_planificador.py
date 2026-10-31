"""Pruebas automatizadas del modelo, simulación y planificador."""

from datetime import date, timedelta
from pathlib import Path
import unittest

from monitoreo.demo import cargar_demo
from monitoreo.modelo import (
    Alojamiento,
    Configuracion,
    Equipo,
    Persona,
    Punto,
    Repositorio,
    Vehiculo,
    calcular_alertas,
    normalizar,
)
from monitoreo.planificador import cumplimiento, evaluar_plan, optimizar_dia, plan_a_dict, planificar


class TestModeloYValidacion(unittest.TestCase):
    def test_validacion_coordenadas_y_rangos(self):
        p = Punto("ag-01", "Río", 7.1, -73.8, "AGUA", duracion_min=45)
        normalizar(p)
        self.assertEqual(p.codigo, "AG-01")
        self.assertEqual(p.matriz, "agua")

        with self.assertRaises(ValueError):
            normalizar(Punto("AG-02", "Lat inválida", 95.0, -73.8))
        with self.assertRaises(ValueError):
            normalizar(Punto("AG-03", "Duración inválida", 7.0, -73.8, duracion_min=0))
        with self.assertRaises(ValueError):
            normalizar(Punto("AG-04", "Ventana invertida", 7.0, -73.8, hora_desde="14:00", hora_hasta="10:00"))
        with self.assertRaises(ValueError):
            normalizar(Vehiculo("ABC-123", capacidad=0))

    def test_demo_no_sobreescribe_sin_respaldo(self):
        tmp = Path("tests_tmp_repo.json")
        bak = Path("tests_tmp_repo.bak.json")
        try:
            tmp.write_text('{"personal": [], "puntos": []}', encoding="utf-8")
            repo = Repositorio(tmp)
            cargar_demo(repo, respaldar=True)
            self.assertTrue(bak.exists())
            self.assertGreater(len(repo.puntos), 10)
        finally:
            tmp.unlink(missing_ok=True)
            bak.unlink(missing_ok=True)


class TestPlanificador(unittest.TestCase):
    def setUp(self):
        self.tmp = Path("tests_tmp_plan.json")
        self.repo = Repositorio(self.tmp)
        cargar_demo(self.repo, respaldar=False)
        self.repo.config.usar_osrm = False  # pruebas rápidas y deterministas sin red

    def tearDown(self):
        self.tmp.unlink(missing_ok=True)

    def test_planificar_y_evaluar_demo(self):
        inicio = date.today() + timedelta(days=1)
        puntos = [p for p in self.repo.puntos if p.activo]
        plan = planificar(self.repo, puntos, inicio, max_dias=15, verbose=False)
        self.assertGreater(len(plan.dias), 0)

        # Verificar que toda instalación de 24h programe también su retiro
        instalaciones = [t.codigo for pd in plan.dias for t in pd.ruta if t.tipo == "instalacion"]
        retiros = [t.codigo for pd in plan.dias for t in pd.ruta if t.tipo == "retiro"]
        self.assertEqual(sorted(instalaciones), sorted(retiros))

        # Serializar y reevaluar
        d = plan_a_dict(plan)
        re_plan = evaluar_plan(self.repo, d)
        self.assertEqual(len(re_plan.dias), len(plan.dias))
        for pd in re_plan.dias:
            self.assertEqual(pd.avisos, [], f"Avisos inesperados en {pd.dia} {pd.cuadrilla.id}: {pd.avisos}")

    def test_aviso_racha_dias_consecutivos(self):
        self.repo.config.max_dias_consecutivos = 2
        inicio = date(2026, 11, 2)  # Lunes
        persona = self.repo.personal[0].nombre
        veh = self.repo.vehiculos[0].placa
        d = {
            "id": "test-racha",
            "nombre": "Test Racha",
            "fecha_inicio": inicio.isoformat(),
            "dias": [
                {"fecha": (inicio + timedelta(days=i)).isoformat(), "cuadrilla": "C1", "vehiculo": veh,
                 "integrantes": [persona], "origen": "__BASE__", "destino": "__BASE__", "viaje": "", "tareas": []}
                for i in range(3)
            ],
            "pendientes": [],
        }
        plan = evaluar_plan(self.repo, d)
        self.assertTrue(any("días consecutivos" in a for a in plan.dias[2].avisos))

    def test_optimizar_dia_y_cumplimiento(self):
        inicio = date.today() + timedelta(days=1)
        plan = planificar(self.repo, [p for p in self.repo.puntos if p.activo][:6], inicio, verbose=False)
        d = plan_a_dict(plan)
        d = optimizar_dia(self.repo, d, 0)
        d["dias"][0]["tareas"][0]["estado"] = "ejecutado"
        re_plan = evaluar_plan(self.repo, d)
        cu = cumplimiento(re_plan)
        self.assertGreater(cu["porcentaje"], 0)


if __name__ == "__main__":
    unittest.main()

