// Scriptable Widget: Estatus de Servicios ECCSA (compacto)
const API_URL = "https://admon.ecc-sa.com.mx/api/estatus-servicios/api/v1/widget";

const COLORES = {
    verde: "#22c55e",
    amarillo: "#eab308",
    rojo: "#ef4444",
    gris: "#6b7280"
};

const SF_SYMBOLS = {
    verde: "checkmark.circle.fill",
    amarillo: "exclamationmark.triangle.fill",
    rojo: "xmark.circle.fill",
    gris: "questionmark.circle.fill"
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
    widget.setPadding(6, 8, 6, 8);

    if (!data) {
        const icon = widget.addImage(SFSymbol.named("wifi.slash").image);
        icon.tintColor = Color.white();
        icon.imageSize = new Size(20, 20);
        const text = widget.addText("Sin conexion");
        text.textColor = Color.white();
        text.font = Font.systemFont(10);
        return widget;
    }

    const hasRed = data.rojos > 0;
    const hasYellow = data.amarillos > 0;
    const allGreen = data.rojos === 0 && data.amarillos === 0;

    // Color de fondo segun estatus global
    if (hasRed) {
        widget.backgroundColor = new Color("#1a0a0a");
    } else if (hasYellow) {
        widget.backgroundColor = new Color("#1a1a0a");
    } else {
        widget.backgroundColor = new Color("#0a1a0a");
    }

    // Header compacto
    const header = widget.addStack();
    header.layoutHorizontally();
    header.centerAlignContent();

    const title = header.addText("Estatus");
    title.textColor = Color.white();
    title.font = Font.boldSystemFont(11);
    header.addSpacer();

    const globalIcon = header.addImage(SFSymbol.named(SF_SYMBOLS[data.global] || "questionmark.circle.fill").image);
    globalIcon.tintColor = new Color(COLORES[data.global] || "#6b7280");
    globalIcon.imageSize = new Size(14, 14);

    widget.addSpacer(3);

    // Resumen visual compacto: 3 numeros con iconos
    const resumen = widget.addStack();
    resumen.layoutHorizontally();
    resumen.centerAlignContent();

    // Verde
    const vStack = resumen.addStack();
    vStack.layoutHorizontally();
    vStack.centerAlignContent();
    const vIcon = vStack.addImage(SFSymbol.named("checkmark.circle.fill").image);
    vIcon.tintColor = new Color("#22c55e");
    vIcon.imageSize = new Size(10, 10);
    vStack.addSpacer(2);
    const vNum = vStack.addText(String(data.verdes));
    vNum.textColor = new Color("#22c55e");
    vNum.font = Font.boldSystemFont(12);

    resumen.addSpacer(8);

    // Amarillo
    const aStack = resumen.addStack();
    aStack.layoutHorizontally();
    aStack.centerAlignContent();
    const aIcon = aStack.addImage(SFSymbol.named("exclamationmark.triangle.fill").image);
    aIcon.tintColor = new Color("#eab308");
    aIcon.imageSize = new Size(10, 10);
    aStack.addSpacer(2);
    const aNum = aStack.addText(String(data.amarillos));
    aNum.textColor = new Color("#eab308");
    aNum.font = Font.boldSystemFont(12);

    resumen.addSpacer(8);

    // Rojo
    const rStack = resumen.addStack();
    rStack.layoutHorizontally();
    rStack.centerAlignContent();
    const rIcon = rStack.addImage(SFSymbol.named("xmark.circle.fill").image);
    rIcon.tintColor = new Color("#ef4444");
    rIcon.imageSize = new Size(10, 10);
    rStack.addSpacer(2);
    const rNum = rStack.addText(String(data.rojos));
    rNum.textColor = new Color("#ef4444");
    rNum.font = Font.boldSystemFont(12);

    widget.addSpacer(4);

    // Separador
    const sep = widget.addStack();
    sep.backgroundColor = new Color(hasRed ? "#ef4444" : hasYellow ? "#eab308" : "#22c55e");
    sep.size = new Size(0, 2);

    widget.addSpacer(3);

    // Si hay rojos, mostrar solo los rojos primero (enfoque en problemas)
    // Si no, mostrar todos
    let serviciosMostrar = data.servicios || [];
    if (hasRed) {
        // Mostrar rojos primero, luego amarillos, luego verdes
        const rojos = serviciosMostrar.filter(s => s.estatus === "rojo");
        const amarillos = serviciosMostrar.filter(s => s.estatus === "amarillo");
        const verdes = serviciosMostrar.filter(s => s.estatus === "verde");
        serviciosMostrar = [...rojos, ...amarillos, ...verdes];
    }

    // Lista compacta: icono + nombre + estatus (sin texto de detalle)
    const maxServicios = 6;
    const servicios = serviciosMostrar.slice(0, maxServicios);
    for (const svc of servicios) {
        const row = widget.addStack();
        row.layoutHorizontally();
        row.centerAlignContent();

        const icon = row.addImage(SFSymbol.named(
            svc.nombre === "Microsoft 365" ? "envelope.fill" :
            svc.nombre === "GoDaddy" ? "globe" :
            svc.nombre === "Cloudflare" ? "cloud.fill" :
            svc.nombre === "Admon" ? "list.bullet.clipboard.fill" :
            svc.nombre === "Field" ? "iphone" :
            svc.nombre === "Dashboard" ? "chart.bar.fill" :
            svc.nombre === "Mailbox" ? "tray.fill" :
            svc.nombre === "Colaboradores" ? "person.2.fill" :
            svc.nombre === "WorkersAdmon" ? "gearshape.2.fill" :
            svc.nombre === "SQL Server" ? "cylinder.split.1x2.fill" :
            svc.nombre === "WebbApps Server" ? "server.rack" :
            "circle.fill"
        ).image);
        icon.tintColor = new Color(COLORES[svc.estatus] || "#6b7280");
        icon.imageSize = new Size(10, 10);
        row.addSpacer(3);

        const name = row.addText(svc.nombre);
        name.textColor = Color.white();
        name.font = Font.systemFont(9);
        name.lineLimit = 1;
        row.addSpacer();

        const status = row.addImage(SFSymbol.named(SF_SYMBOLS[svc.estatus] || "questionmark.circle.fill").image);
        status.tintColor = new Color(COLORES[svc.estatus] || "#6b7280");
        status.imageSize = new Size(10, 10);

        widget.addSpacer(1);
    }

    // Si hay mas servicios de los mostrados
    if (serviciosMostrar.length > maxServicios) {
        const more = widget.addText("+" + (serviciosMostrar.length - maxServicios) + " mas");
        more.textColor = new Color("#6b7280");
        more.font = Font.systemFont(8);
    }

    widget.addSpacer(2);

    // Footer minimalista
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