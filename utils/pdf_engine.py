"""
PDF Engine — Generación de facturas en PDF usando ReportLab
"""
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from utils.invoice_engine import InvoiceCalculation


# ─────────────────────────────────────────────
# Colores corporativos
# ─────────────────────────────────────────────
BRAND_BLUE = colors.HexColor("#1a56db")
BRAND_DARK = colors.HexColor("#111827")
LIGHT_GRAY = colors.HexColor("#f3f4f6")
MID_GRAY = colors.HexColor("#6b7280")
RED_ALERT = colors.HexColor("#dc2626")
GREEN_OK = colors.HexColor("#059669")


def _fmt(value, moneda: str = "$") -> str:
    try:
        return f"{moneda} {float(value):,.2f}"
    except Exception:
        return f"{moneda} 0.00"


def generate_invoice_pdf(
    calc: InvoiceCalculation,
    hotel_nombre: str,
    hotel_direccion: Optional[str],
    hotel_nombre_fiscal: Optional[str],
    invoice_number: str,
    moneda: str = "$",
    iva_porcentaje: float = 21.0,
) -> bytes:
    """
    Genera el PDF de factura a partir de un InvoiceCalculation.

    Returns:
        bytes: contenido PDF listo para enviar como respuesta HTTP.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Factura {invoice_number}",
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    normal.fontName = "Helvetica"
    normal.fontSize = 9

    h1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=18, textColor=BRAND_BLUE, spaceAfter=4)
    h2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=11, textColor=BRAND_DARK, spaceAfter=3)
    small = ParagraphStyle("small", fontName="Helvetica", fontSize=8, textColor=MID_GRAY)
    right = ParagraphStyle("right", fontName="Helvetica", fontSize=9, alignment=TA_RIGHT)
    right_bold = ParagraphStyle("right_bold", fontName="Helvetica-Bold", fontSize=10, alignment=TA_RIGHT)

    elements = []
    W = A4[0] - 4 * cm  # usable width

    # ── Header ──────────────────────────────────────
    header_data = [
        [
            Paragraph(hotel_nombre_fiscal or hotel_nombre, h1),
            Paragraph(f"<b>FACTURA</b>", ParagraphStyle("inv", fontName="Helvetica-Bold", fontSize=22,
                                                          textColor=BRAND_BLUE, alignment=TA_RIGHT)),
        ],
        [
            Paragraph(hotel_direccion or "", small),
            Paragraph(f"Nº <b>{invoice_number}</b>", ParagraphStyle("invnum", fontName="Helvetica-Bold",
                                                                       fontSize=11, alignment=TA_RIGHT)),
        ],
        [
            Paragraph("", small),
            Paragraph(f"Fecha: <b>{date.today().strftime('%d/%m/%Y')}</b>",
                      ParagraphStyle("fdate", fontName="Helvetica", fontSize=9, alignment=TA_RIGHT)),
        ],
    ]
    header_table = Table(header_data, colWidths=[W * 0.6, W * 0.4])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(header_table)
    elements.append(HRFlowable(width="100%", thickness=1, color=BRAND_BLUE, spaceAfter=10))

    # ── Datos del huésped ────────────────────────────
    elements.append(Paragraph("DATOS DEL HUÉSPED", h2))
    guest_data = [
        ["Huésped:", calc.cliente_nombre or "—"],
        ["Habitación:", f"Nº {calc.room_numero} — {calc.room_type_name}"],
        ["Check-in:",
         calc.checkin_date.strftime("%d/%m/%Y") if calc.checkin_date else "—"],
        ["Check-out:",
         (calc.checkout_candidate_date or calc.checkout_planned_date).strftime("%d/%m/%Y")
         if (calc.checkout_candidate_date or calc.checkout_planned_date) else "—"],
        ["Noches:", str(calc.final_nights)],
    ]
    guest_tbl = Table(guest_data, colWidths=[3.5 * cm, W - 3.5 * cm])
    guest_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TEXTCOLOR", (0, 0), (0, -1), MID_GRAY),
    ]))
    elements.append(guest_tbl)
    elements.append(Spacer(1, 10))

    # ── Detalle de cargos ────────────────────────────
    elements.append(Paragraph("DETALLE", h2))

    charge_rows = [
        [
            Paragraph("<b>Descripción</b>", normal),
            Paragraph("<b>Cant.</b>", ParagraphStyle("ch", fontName="Helvetica-Bold", fontSize=9, alignment=TA_RIGHT)),
            Paragraph("<b>P. Unitario</b>", ParagraphStyle("ch", fontName="Helvetica-Bold", fontSize=9, alignment=TA_RIGHT)),
            Paragraph("<b>Total</b>", ParagraphStyle("ch", fontName="Helvetica-Bold", fontSize=9, alignment=TA_RIGHT)),
        ]
    ]

    # Alojamiento
    charge_rows.append([
        Paragraph(f"Alojamiento — {calc.room_type_name} ({calc.final_nights} noche{'s' if calc.final_nights != 1 else ''})", normal),
        Paragraph(str(calc.final_nights), right),
        Paragraph(_fmt(calc.nightly_rate, moneda), right),
        Paragraph(_fmt(calc.room_subtotal, moneda), right),
    ])

    # Consumos / cargos extra
    for item in calc.charges_breakdown:
        sign = -1 if item["type"] in ("discount",) else 1
        charge_rows.append([
            Paragraph(item["description"], normal),
            Paragraph(f"{item['quantity']:.0f}", right),
            Paragraph(_fmt(abs(item["unit_price"]) * sign, moneda), right),
            Paragraph(_fmt(item["total"], moneda), right),
        ])

    charge_tbl = Table(
        charge_rows,
        colWidths=[W * 0.5, W * 0.12, W * 0.19, W * 0.19],
    )
    charge_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(charge_tbl)
    elements.append(Spacer(1, 8))

    # ── Totales ──────────────────────────────────────
    totals_data = []

    def _row(label, value, bold=False, color=None):
        style = ParagraphStyle(
            "tot",
            fontName="Helvetica-Bold" if bold else "Helvetica",
            fontSize=10 if bold else 9,
            alignment=TA_RIGHT,
            textColor=color or BRAND_DARK,
        )
        return [
            Paragraph("", normal),
            Paragraph(label, ParagraphStyle("totl", fontName="Helvetica-Bold" if bold else "Helvetica",
                                             fontSize=10 if bold else 9, alignment=TA_RIGHT, textColor=MID_GRAY)),
            Paragraph(value, style),
        ]

    totals_data.append(_row("Subtotal alojamiento:", _fmt(calc.room_subtotal, moneda)))
    if calc.charges_total:
        totals_data.append(_row("Cargos adicionales:", _fmt(calc.charges_total, moneda)))
    if calc.discounts_total:
        totals_data.append(_row("Descuentos:", f"- {_fmt(calc.discounts_total, moneda)}", color=GREEN_OK))
    totals_data.append(_row(f"IVA ({iva_porcentaje:.0f}%):", _fmt(calc.taxes_total, moneda)))
    totals_data.append(_row("TOTAL:", _fmt(calc.grand_total, moneda), bold=True, color=BRAND_BLUE))
    totals_data.append(_row("Pagado:", _fmt(calc.payments_total, moneda), color=GREEN_OK))
    saldo_color = RED_ALERT if calc.balance > 0 else GREEN_OK
    totals_data.append(_row("Saldo:", _fmt(calc.balance, moneda), bold=True, color=saldo_color))

    totals_tbl = Table(totals_data, colWidths=[W * 0.45, W * 0.30, W * 0.25])
    totals_tbl.setStyle(TableStyle([
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEABOVE", (1, -3), (-1, -3), 0.5, BRAND_BLUE),  # línea antes de TOTAL
    ]))
    elements.append(totals_tbl)

    # ── Pagos detallados ──────────────────────────────
    if calc.payments_breakdown:
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("PAGOS REGISTRADOS", h2))
        pay_rows = [[
            Paragraph("<b>Método</b>", normal),
            Paragraph("<b>Referencia</b>", normal),
            Paragraph("<b>Monto</b>", ParagraphStyle("ph", fontName="Helvetica-Bold", fontSize=9, alignment=TA_RIGHT)),
        ]]
        for p in calc.payments_breakdown:
            pay_rows.append([
                Paragraph(str(p.get("metodo", "—")).capitalize(), normal),
                Paragraph(str(p.get("referencia", "—") or "—"), normal),
                Paragraph(_fmt(p["monto"], moneda), right),
            ])
        pay_tbl = Table(pay_rows, colWidths=[W * 0.25, W * 0.50, W * 0.25])
        pay_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(pay_tbl)

    # ── Footer ───────────────────────────────────────
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=MID_GRAY))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(
        f"Documento generado por {hotel_nombre} · {invoice_number} · {date.today().strftime('%d/%m/%Y')}",
        ParagraphStyle("footer", fontName="Helvetica", fontSize=7, textColor=MID_GRAY, alignment=TA_CENTER),
    ))

    doc.build(elements)
    return buffer.getvalue()
