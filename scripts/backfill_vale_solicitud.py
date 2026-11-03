"""Backfill IdSolicitudVale in HUB_OxxoGasVales.

Matches vales to solicitudes by date (±7 days).
Run once after applying migration 0061.
"""
import pymssql

conn = pymssql.connect(server="10.188.141.15", user="sa", password="eyccazo", database="ECCSA_Admon", timeout=10, autocommit=True)
cursor = conn.cursor(as_dict=True)

# Get vales without IdSolicitudVale
cursor.execute("""
    SELECT Id, Fecha FROM HUB_OxxoGasVales
    WHERE IdSolicitudVale IS NULL
""")
vales = cursor.fetchall()
print(f"Vales sin IdSolicitudVale: {len(vales)}")

updated = 0
for v in vales:
    cursor.execute("""
        SELECT TOP 1 Id FROM HUB_SolicitudVales
        WHERE FechaSolicitud >= DATEADD(day, -7, %s)
          AND FechaSolicitud <= DATEADD(day, 7, %s)
          AND Id NOT IN (SELECT IdSolicitudVale FROM HUB_OxxoGasVales WHERE IdSolicitudVale IS NOT NULL)
        ORDER BY ABS(DATEDIFF(day, FechaSolicitud, %s))
    """, (v["Fecha"], v["Fecha"], v["Fecha"]))
    sol = cursor.fetchone()
    if sol:
        cursor.execute("UPDATE HUB_OxxoGasVales SET IdSolicitudVale = %s WHERE Id = %s", (sol["Id"], v["Id"]))
        updated += 1

print(f"Vales actualizados: {updated}")
conn.close()