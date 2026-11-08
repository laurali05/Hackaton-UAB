# 404:Brain Cells — Reto de horarios y espacios

Propuesta del equipo **404:Brain Cells** para el reto de la Escuela de Ingeniería de la UAB (UAB THE HACK! 2026). Analizamos la ocupación de los espacios y preparamos propuestas de asignación de aulas y horarios para el segundo semestre.

El reto trabaja con 17.026 sesiones, 56 espacios y datos seudonimizados del curso 2026-27. Las propuestas deben respetar las restricciones del reto —capacidad, tipo de aula, sesiones compartidas y reserva mínima de aulas, entre otras— y reducir las horas muertas, los desplazamientos y los cambios respecto al horario de partida.

## Análisis de los datos

Las figuras de esta sección describen la **situación de partida** y ayudan a identificar los cuellos de botella antes de generar una propuesta nueva.

### 1. Ocupación media por día y franja

En el segundo semestre, la ocupación media más alta se concentra los martes y jueves a las 10:30, con 7 aulas ocupadas de media. El jueves a las 12:30 también se observa un pico de 7. Por la tarde, la ocupación es mucho menor.

![Mapa de calor de la ocupación media de aulas por día y franja en el segundo semestre](grafics/1_heatmap_ocupacio_s2.png)

### 2. Pico de simultaneidad por la mañana

El pico de partida es de **15 clases simultáneas**. Para la comparación del reto se consideran 19 aulas ordinarias disponibles, ya que se reservan dos de las 21. El pico actual queda por debajo de ese límite, pero la demanda se concentra en unas pocas franjas.

![Clases simultáneas por la mañana comparadas con la capacidad neta de 19 aulas](grafics/2_pico_matinal_vs_capacitat.png)

### 3. Cohortes con más sesiones fuera del turno previsto

La figura muestra las cohortes que acumulan más sesiones fuera del turno que les corresponde según el modelo del reto. GEI de 3.º y 4.º destaca especialmente, por lo que sería uno de los grupos que más cambios necesitaría con la reorganización de turnos.

![Diez cohortes con más sesiones fuera de turno en el segundo semestre](grafics/3_fora_de_torn_top_cohorts.png)

### 4. Horas de aula sin asignar y disponibilidad

La figura compara **6.539 horas-aula** de sesiones que no tenían aula asignada con **19.712 horas** disponibles en las 19 aulas ordinarias. Es una comparación de volumen agregado: por sí sola no garantiza que cada sesión tenga un aula compatible y libre en su franja, con capacidad suficiente.

![Horas de aula sin asignar comparadas con las horas disponibles](grafics/4_balanc_hores_aula.png)

### 5. Exceso de aforo en el horario de partida

En la partida hay **43 sesiones con exceso de aforo repartidas en dos grupos**: 29 asociadas al aula Q4/0011 y 14 a Q3/0003. La propuesta de aulas debe resolver estos casos asignando espacios con capacidad suficiente.

![Sesiones con exceso de aforo en el aula de partida](grafics/5_excessos_aforament.png)

## Propuestas del reto

| Punto | Objetivo | Script y salida principal |
| --- | --- | --- |
| 5.1 | Asignar aulas en el segundo semestre sin cambiar días ni horas | `solucio_5_1.py` → `proposta-aules.csv` |
| 5.2 | Reorganizar los turnos y optimizar el horario | `solucio_5_2.py` → `proposta-torns.csv` |
| 5.3 | Adaptar la propuesta al escenario de imprevistos | `solucio_5_3.py` → `proposta-imprevist.csv` |
| 5.4 | Incorporar el nuevo grado de 40 plazas | `solucions_5_4.py` → `proposta-grau-nou.csv` |

El repositorio también contiene el análisis, el verificador del reto en `horaris/`, los datos de entrada en `paquet/` y archivos auxiliares con propuestas e informes. Consulta [`paquet/DICCIONARI.md`](paquet/DICCIONARI.md) para conocer las columnas y las limitaciones de los datos.

## Ejecución

Ejecuta los comandos desde la raíz del repositorio. Se necesita Python 3.10 o superior. El verificador solo usa la biblioteca estándar; los scripts de solución necesitan `pandas`.

### Comprobar la partida del punto 5.1

```powershell
python -m horaris check paquet/proposta_partida.csv --semestre 2 --nomes-aules
```

### Generar y validar el punto 5.1

```powershell
python solucio_5_1.py
python -m horaris check proposta-aules.csv --semestre 2 --nomes-aules --json informe-5_1.json --violacions violacions-5_1.csv
```

### Generar y validar los demás puntos

```powershell
python solucio_5_2.py
python -m horaris check proposta-torns.csv --semestre 2 --json informe-5_2.json --violacions violacions-5_2.csv

python solucio_5_3.py --base proposta-torns.csv --check

python solucions_5_4.py proposta-torns.csv --out proposta-grau-nou.csv --check
```

La comprobación principal es el **veredicto del verificador**, no una estimación de puntuación. El informe puede mostrar incumplimientos heredados del horario de partida; estos no cuentan como incumplimientos nuevos de la propuesta.

## Datos y uso responsable

Los datos del paquete están seudonimizados, pero no son anónimos. Se usan únicamente para este reto: no intentes identificar a ninguna persona ni publiques o compartas los datos fuera del contexto autorizado de la hackatón.

## Equipo

**404:Brain Cells** · UAB THE HACK! 2026
