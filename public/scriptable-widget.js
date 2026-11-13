// Scriptable Widget: Estatus de Servicios ECCSA (compacto)
const API_URL = "https://admon.ecc-sa.com.mx/api/estatus-servicios/api/v1/widget";

const COLORES = {
    verde: "#22c55e",
    amarillo: "#eab308",
    rojo: "#ef4444",
    gris: "#6b7280"
};

function safeSymbol(stack, name, size, color) {
    try {
        const sym = SFSymbol.named(name);
        if (sym && sym.image) {
            const img = stack.addImage(sym.image);
            img.tintColor = new Color(color);
            img.imageSize = new Size(size, size);
            return;
        }
    } catch (e) {}
    // Fallback: circulo de color
    const t = stack.addText("\u{25CF}");
    t.textColor = new Color(color);
    t.font = Font.systemFont(size);
}

async function fetchData() {
    try {
        const req = new Request(API_URL);
        const data = await req.loadJSON();
        return data;
    } catch (e) {
        return null;
    }
}

function crearWidget(data, widgetSize) {
    const widget = new ListWidget();
    widget.backgroundColor = new Color("#0f172a");
    widget.setPadding(6, 8, 6, 8);

    if (!data) {
        safeSymbol(widget, "wifi.slash", 20, "#ffffff");
        const text = widget.addText("Sin conexion");
        text.textColor = Color.white();
        text.font = Font.systemFont(10);
        return widget;
    }

    const isSmall = widgetSize === "small";

    const hasRed = data.rojos > 0;
    const hasYellow = data.amarillos > 0;

    if (hasRed) {
        widget.backgroundColor = new Color("#1a0a0a");
    } else if (hasYellow) {
        widget.backgroundColor = new Color("#1a1a0a");
    } else {
        widget.backgroundColor = new Color("#0a1a0a");
    }

    const header = widget.addStack();
    header.layoutHorizontally();
    header.centerAlignContent();

    const title = header.addText("Estatus");
    title.textColor = Color.white();
    title.font = Font.boldSystemFont(isSmall ? 11 : 13);
    header.addSpacer();

    const globalStack = header.addStack();
    globalStack.layoutVertically();
    globalStack.centerAlignContent();

    const statusNames = {
        verde: "checkmark.circle.fill",
        amarillo: "exclamationmark.triangle.fill",
        rojo: "xmark.circle.fill",
        gris: "questionmark.circle.fill"
    };
    safeSymbol(globalStack, statusNames[data.global] || "questionmark.circle.fill", isSmall ? 14 : 18, COLORES[data.global] || "#6b7280");

    const globalLabel = globalStack.addText((data.global || "gris").toUpperCase());
    globalLabel.textColor = new Color(COLORES[data.global] || "#6b7280");
    globalLabel.font = Font.boldSystemFont(7);

    widget.addSpacer(3);

    const resumen = widget.addStack();
    resumen.layoutHorizontally();
    resumen.centerAlignContent();

    // Verde
    const vStack = resumen.addStack();
    vStack.layoutHorizontally();
    vStack.centerAlignContent();
    safeSymbol(vStack, "checkmark.circle.fill", 10, "#22c55e");
    vStack.addSpacer(2);
    const vNum = vStack.addText(String(data.verdes));
    vNum.textColor = new Color("#22c55e");
    vNum.font = Font.boldSystemFont(isSmall ? 10 : 12);

    resumen.addSpacer(6);

    // Amarillo
    const aStack = resumen.addStack();
    aStack.layoutHorizontally();
    aStack.centerAlignContent();
    safeSymbol(aStack, "exclamationmark.triangle.fill", 10, "#eab308");
    aStack.addSpacer(2);
    const aNum = aStack.addText(String(data.amarillos));
    aNum.textColor = new Color("#eab308");
    aNum.font = Font.boldSystemFont(isSmall ? 10 : 12);

    resumen.addSpacer(6);

    // Rojo
    const rStack = resumen.addStack();
    rStack.layoutHorizontally();
    rStack.centerAlignContent();
    safeSymbol(rStack, "xmark.circle.fill", 10, "#ef4444");
    rStack.addSpacer(2);
    const rNum = rStack.addText(String(data.rojos));
    rNum.textColor = new Color("#ef4444");
    rNum.font = Font.boldSystemFont(isSmall ? 10 : 12);

    resumen.addSpacer(8);

    // Total
    const totalStack = resumen.addStack();
    totalStack.layoutVertically();
    totalStack.centerAlignContent();
    const totalNum = totalStack.addText(String(data.total));
    totalNum.textColor = Color.white();
    totalNum.font = Font.boldSystemFont(isSmall ? 10 : 12);
    const totalLabel = totalStack.addText("total");
    totalLabel.textColor = new Color("#6b7280");
    totalLabel.font = Font.systemFont(7);

    widget.addSpacer(4);

    const sep = widget.addStack();
    sep.backgroundColor = new Color(hasRed ? "#ef4444" : hasYellow ? "#eab308" : "#22c55e");
    sep.size = new Size(0, 2);

    widget.addSpacer(3);

    let serviciosMostrar = data.servicios || [];
    if (hasRed) {
        const rojos = serviciosMostrar.filter(s => s.estatus === "rojo");
        const amarillos = serviciosMostrar.filter(s => s.estatus === "amarillo");
        const verdes = serviciosMostrar.filter(s => s.estatus === "verde");
        serviciosMostrar = [...rojos, ...amarillos, ...verdes];
    }

    const maxServicios = isSmall ? 4 : isMedium ? 6 : 10;
    const servicios = serviciosMostrar.slice(0, maxServicios);

    const servicioIcons = {
        "Microsoft 365": "envelope.fill",
        "GoDaddy": "globe",
        "Cloudflare": "cloud.fill",
        "Admon": "list.bullet.clipboard.fill",
        "Field": "iphone",
        "Dashboard": "chart.bar.fill",
        "Mailbox": "tray.fill",
        "Colaboradores": "person.2.fill",
        "WorkersAdmon": "gearshape.2.fill",
        "SQL Server": "cylinder.split.1x2.fill",
        "WebbApps Server": "server.rack"
    };

    for (const svc of servicios) {
        const row = widget.addStack();
        row.layoutHorizontally();
        row.centerAlignContent();

        safeSymbol(row, servicioIcons[svc.nombre] || "circle.fill", 10, COLORES[svc.estatus] || "#6b7280");
        row.addSpacer(3);

        const name = row.addText(svc.nombre);
        name.textColor = Color.white();
        name.font = Font.systemFont(isSmall ? 9 : 10);
        name.lineLimit = 1;
        row.addSpacer();

        const statusSymbol = svc.estatus === "verde" ? "checkmark.circle.fill" :
                            svc.estatus === "amarillo" ? "exclamationmark.triangle.fill" :
                            svc.estatus === "rojo" ? "xmark.circle.fill" :
                            "questionmark.circle.fill";
        safeSymbol(row, statusSymbol, 10, COLORES[svc.estatus] || "#6b7280");

        widget.addSpacer(1);
    }

    if (serviciosMostrar.length > maxServicios) {
        const more = widget.addText("+" + (serviciosMostrar.length - maxServicios) + " mas");
        more.textColor = new Color("#6b7280");
        more.font = Font.systemFont(8);
    }

    widget.addSpacer(2);

    const footer = widget.addText(data.actualizado || "\u{2014}");
    footer.textColor = new Color("#6b7280");
    footer.font = Font.systemFont(7);

    return widget;
}

const data = await fetchData();

let widgetSize = "small";
if (config.widgetFamily === "medium") widgetSize = "medium";
else if (config.widgetFamily === "large") widgetSize = "large";

const widget = crearWidget(data, widgetSize);

if (config.runsInWidget) {
    Script.setWidget(widget);
} else {
    widget.presentSmall();
}

Script.complete();