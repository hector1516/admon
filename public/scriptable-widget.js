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
    widget.setPadding(10, 12, 10, 12);

    if (!data) {
        const text = widget.addText("Sin conexion");
        text.textColor = Color.white();
        text.font = Font.systemFont(14);
        return widget;
    }

    // Header con semaforo global
    const header = widget.addStack();
    header.layoutHorizontally();
    header.centerAlignContent();

    const title = header.addText("Estatus Servicios");
    title.textColor = Color.white();
    title.font = Font.boldSystemFont(13);
    header.addSpacer();

    // Semaforo global grande
    const globalStack = header.addStack();
    globalStack.layoutVertically();
    globalStack.centerAlignContent();
    const globalIcon = globalStack.addText(ICONOS[data.global] || "\u{26AA}");
    globalIcon.font = Font.systemFont(16);
    const globalLabel = globalStack.addText(data.global.toUpperCase());
    globalLabel.textColor = new Color(COLORES[data.global] || "#6b7280");
    globalLabel.font = Font.boldSystemFont(8);

    widget.addSpacer(6);

    // Resumen en barra
    const resumenStack = widget.addStack();
    resumenStack.layoutHorizontally();
    resumenStack.centerAlignContent();

    const verdeStack = resumenStack.addStack();
    verdeStack.layoutVertically();
    verdeStack.centerAlignContent();
    const vNum = verdeStack.addText(String(data.verdes));
    vNum.textColor = new Color("#22c55e");
    vNum.font = Font.boldSystemFont(14);
    const vLabel = verdeStack.addText("OK");
    vLabel.textColor = new Color("#22c55e");
    vLabel.font = Font.systemFont(8);

    resumenStack.addSpacer(8);

    const amarilloStack = resumenStack.addStack();
    amarilloStack.layoutVertically();
    amarilloStack.centerAlignContent();
    const aNum = amarilloStack.addText(String(data.amarillos));
    aNum.textColor = new Color("#eab308");
    aNum.font = Font.boldSystemFont(14);
    const aLabel = amarilloStack.addText("DEG");
    aLabel.textColor = new Color("#eab308");
    aLabel.font = Font.systemFont(8);

    resumenStack.addSpacer(8);

    const rojoStack = resumenStack.addStack();
    rojoStack.layoutVertically();
    rojoStack.centerAlignContent();
    const rNum = rojoStack.addText(String(data.rojos));
    rNum.textColor = new Color("#ef4444");
    rNum.font = Font.boldSystemFont(14);
    const rLabel = rojoStack.addText("DOWN");
    rLabel.textColor = new Color("#ef4444");
    rLabel.font = Font.systemFont(8);

    widget.addSpacer(6);

    // Separador
    const sep = widget.addStack();
    sep.backgroundColor = new Color("#334155");
    sep.size = new Size(0, 1);

    widget.addSpacer(4);

    // Lista de servicios
    const servicios = (data.servicios || []).slice(0, 10);
    for (const svc of servicios) {
        const row = widget.addStack();
        row.layoutHorizontally();
        row.centerAlignContent();

        const name = row.addText(svc.nombre);
        name.textColor = Color.white();
        name.font = Font.systemFont(10);
        name.lineLimit = 1;
        row.addSpacer();

        const status = row.addText(ICONOS[svc.estatus] || "\u{26AA}");
        status.font = Font.systemFont(10);

        widget.addSpacer(2);
    }

    widget.addSpacer(4);

    // Footer
    const footer = widget.addText("Actualizado: " + (data.actualizado || "\u{2014}"));
    footer.textColor = new Color("#6b7280");
    footer.font = Font.systemFont(8);

    return widget;
}

const data = await fetchData();
const widget = crearWidget(data);

if (config.runsInWidget) {
    Script.setWidget(widget);
} else {
    widget.presentMedium();
}

Script.complete();