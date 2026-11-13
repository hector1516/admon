// Scriptable Widget: Estatus de Servicios ECCSA
// Colocar en la app Scriptable de iPhone
// URL de la API
const API_URL = "https://admon.ecc-sa.com.mx/api/estatus-servicios/api/v1/widget";

// Colores por estatus
const COLORES = {
    verde: "#22c55e",
    amarillo: "#eab308",
    rojo: "#ef4444",
    gris: "#6b7280"
};

// SF Symbols para cada estatus
const SF_SYMBOLS = {
    verde: "checkmark.circle.fill",
    amarillo: "exclamationmark.triangle.fill",
    rojo: "xmark.circle.fill",
    gris: "questionmark.circle.fill"
};

// SF Symbols para servicios
const SF_SERVICIO = {
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
    widget.setPadding(8, 10, 8, 10);

    if (!data) {
        const icon = widget.addImage(SFSymbol.named("wifi.slash").image);
        icon.tintColor = Color.white();
        icon.imageSize = new Size(24, 24);
        const text = widget.addText("Sin conexion");
        text.textColor = Color.white();
        text.font = Font.systemFont(12);
        return widget;
    }

    const isSmall = widgetSize === "small";
    const isMedium = widgetSize === "medium";
    const isLarge = widgetSize === "large";

    // Header
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
    const globalIcon = globalStack.addImage(SFSymbol.named(SF_SYMBOLS[data.global] || "questionmark.circle.fill").image);
    globalIcon.tintColor = new Color(COLORES[data.global] || "#6b7280");
    globalIcon.imageSize = new Size(isSmall ? 14 : 18, isSmall ? 14 : 18);
    const globalLabel = globalStack.addText(data.global.toUpperCase());
    globalLabel.textColor = new Color(COLORES[data.global] || "#6b7280");
    globalLabel.font = Font.boldSystemFont(7);

    widget.addSpacer(4);

    // Resumen en barra visual
    const resumenStack = widget.addStack();
    resumenStack.layoutHorizontally();
    resumenStack.centerAlignContent();

    // Verde
    const vStack = resumenStack.addStack();
    vStack.layoutVertically();
    vStack.centerAlignContent();
    const vIcon = vStack.addImage(SFSymbol.named("checkmark.circle.fill").image);
    vIcon.tintColor = new Color("#22c55e");
    vIcon.imageSize = new Size(12, 12);
    const vNum = vStack.addText(String(data.verdes));
    vNum.textColor = new Color("#22c55e");
    vNum.font = Font.boldSystemFont(isSmall ? 10 : 12);

    resumenStack.addSpacer(6);

    // Amarillo
    const aStack = resumenStack.addStack();
    aStack.layoutVertically();
    aStack.centerAlignContent();
    const aIcon = aStack.addImage(SFSymbol.named("exclamationmark.triangle.fill").image);
    aIcon.tintColor = new Color("#eab308");
    aIcon.imageSize = new Size(12, 12);
    const aNum = aStack.addText(String(data.amarillos));
    aNum.textColor = new Color("#eab308");
    aNum.font = Font.boldSystemFont(isSmall ? 10 : 12);

    resumenStack.addSpacer(6);

    // Rojo
    const rStack = resumenStack.addStack();
    rStack.layoutVertically();
    rStack.centerAlignContent();
    const rIcon = rStack.addImage(SFSymbol.named("xmark.circle.fill").image);
    rIcon.tintColor = new Color("#ef4444");
    rIcon.imageSize = new Size(12, 12);
    const rNum = rStack.addText(String(data.rojos));
    rNum.textColor = new Color("#ef4444");
    rNum.font = Font.boldSystemFont(isSmall ? 10 : 12);

    // Total
    resumenStack.addSpacer(8);
    const totalStack = resumenStack.addStack();
    totalStack.layoutVertically();
    totalStack.centerAlignContent();
    const totalNum = totalStack.addText(String(data.total));
    totalNum.textColor = Color.white();
    totalNum.font = Font.boldSystemFont(isSmall ? 10 : 12);
    const totalLabel = totalStack.addText("total");
    totalLabel.textColor = new Color("#6b7280");
    totalLabel.font = Font.systemFont(7);

    widget.addSpacer(4);

    // Separador
    const sep = widget.addStack();
    sep.backgroundColor = new Color("#334155");
    sep.size = new Size(0, 1);

    widget.addSpacer(3);

    // Lista de servicios
    const maxServicios = isSmall ? 4 : isMedium ? 6 : 10;
    const servicios = (data.servicios || []).slice(0, maxServicios);
    for (const svc of servicios) {
        const row = widget.addStack();
        row.layoutHorizontally();
        row.centerAlignContent();

        const icon = row.addImage(SFSymbol.named(SF_SERVICIO[svc.nombre] || "circle.fill").image);
        icon.tintColor = new Color(COLORES[svc.estatus] || "#6b7280");
        icon.imageSize = new Size(10, 10);
        row.addSpacer(3);

        const name = row.addText(svc.nombre);
        name.textColor = Color.white();
        name.font = Font.systemFont(isSmall ? 9 : 10);
        name.lineLimit = 1;
        row.addSpacer();

        const status = row.addImage(SFSymbol.named(SF_SYMBOLS[svc.estatus] || "questionmark.circle.fill").image);
        status.tintColor = new Color(COLORES[svc.estatus] || "#6b7280");
        status.imageSize = new Size(10, 10);

        widget.addSpacer(2);
    }

    widget.addSpacer(3);

    // Footer
    const footer = widget.addText("Act: " + (data.actualizado || "\u{2014}"));
    footer.textColor = new Color("#6b7280");
    footer.font = Font.systemFont(7);

    return widget;
}

const data = await fetchData();

// Detectar tamaño del widget
let widgetSize = "medium";
if (config.widgetFamily === "small") widgetSize = "small";
else if (config.widgetFamily === "large") widgetSize = "large";

const widget = crearWidget(data, widgetSize);

if (config.runsInWidget) {
    Script.setWidget(widget);
} else {
    widget.presentMedium();
}

Script.complete();