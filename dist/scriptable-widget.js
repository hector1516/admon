// Scriptable Widget: Estatus de Servicios ECCSA
// Colocar en la app Scriptable de iPhone
// URL de la API (cambiar por la URL real de produccion)
const API_URL = "https://admon.ecc-sa.com.mx/api/estatus-servicios/api/v1/widget";

// Colores por estatus
const COLORES = {
    verde: "#22c55e",
    amarillo: "#eab308",
    rojo: "#ef4444",
    gris: "#6b7280"
};

const ICONOS = {
    verde: "\u{1F7E2}",
    amarillo: "\u{1F7E1}",
    rojo: "\u{1F534}",
    gris: "\u{26AA}"
};

async function fetchData() {
    try {
        const req = new Request(API_URL);
        const data = await req.loadJSON();
        return data;
    } catch (e) {
        return null;
    }
}

function crearWidget(data) {
    const widget = new ListWidget();
    widget.backgroundColor = new Color("#0f172a");

    if (!data) {
        const text = widget.addText("Sin conexion");
        text.textColor = Color.white();
        text.font = Font.systemFont(12);
        return widget;
    }

    // Header
    const header = widget.addStack();
    header.layoutHorizontally();
    const title = header.addText("Estatus Servicios");
    title.textColor = Color.white();
    title.font = Font.boldSystemFont(12);
    header.addSpacer();
    const globalIcon = header.addText(ICONOS[data.global] || "\u{26AA}");
    globalIcon.font = Font.systemFont(12);

    widget.addSpacer(4);

    // Resumen
    const resumen = widget.addText(data.verdes + "\u{1F7E2} " + data.amarillos + "\u{1F7E1} " + data.rojos + "\u{1F534}");
    resumen.textColor = Color.white();
    resumen.font = Font.systemFont(10);

    widget.addSpacer(4);

    // Lista de servicios (maximo 8 para que quepa)
    const servicios = (data.servicios || []).slice(0, 8);
    for (const svc of servicios) {
        const row = widget.addStack();
        row.layoutHorizontally();
        const icon = row.addText(svc.icono || "\u{1F527}");
        icon.font = Font.systemFont(10);
        row.addSpacer(2);
        const name = row.addText(svc.nombre);
        name.textColor = Color.white();
        name.font = Font.systemFont(10);
        name.lineLimit = 1;
        row.addSpacer();
        const status = row.addText(ICONOS[svc.estatus] || "\u{26AA}");
        status.font = Font.systemFont(10);
    }

    widget.addSpacer(4);
    const footer = widget.addText("Actualizado: " + (data.actualizado || "\u{2014}"));
    footer.textColor = new Color("#6b7280");
    footer.font = Font.systemFont(8);

    return widget;
}

// Main
const data = await fetchData();
const widget = crearWidget(data);

if (config.runsInWidget) {
    Script.setWidget(widget);
} else {
    widget.presentMedium();
}

Script.complete();