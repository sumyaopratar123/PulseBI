from flask import Flask, render_template, request, send_file
import pandas as pd
import numpy as np
import os
import json

import plotly.express as px
from plotly.utils import PlotlyJSONEncoder

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak
)

app = Flask(__name__)

# =========================================================
# FOLDERS
# =========================================================

UPLOAD_FOLDER = "uploads"
REPORT_FOLDER = "reports"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# =========================================================
# HELPERS
# =========================================================

def chart_json(fig):
    """
    Convert Plotly figure into JSON-safe data.
    """
    return json.dumps(fig, cls=PlotlyJSONEncoder)


def find_column(columns, keywords):
    """
    Automatically detect a relevant business column.
    """
    columns_lower = {
        str(col).lower().strip(): col
        for col in columns
    }

    # Exact / contains matching
    for keyword in keywords:

        keyword = keyword.lower()

        for lower_col, original_col in columns_lower.items():

            if keyword == lower_col:
                return original_col

    for keyword in keywords:

        keyword = keyword.lower()

        for lower_col, original_col in columns_lower.items():

            if keyword in lower_col:
                return original_col

    return None


def clean_dataframe(df):
    """
    Clean uploaded Excel data.
    """

    # Remove completely empty rows
    df = df.dropna(how="all")

    # Remove completely empty columns
    df = df.dropna(axis=1, how="all")

    # Clean column names
    df.columns = [
        str(col).strip().replace("\n", " ")
        for col in df.columns
    ]

    # Convert unnamed columns
    new_columns = []

    for i, col in enumerate(df.columns):

        if str(col).lower().startswith("unnamed"):
            new_columns.append(f"Column_{i + 1}")
        else:
            new_columns.append(col)

    df.columns = new_columns

    return df


# =========================================================
# BUSINESS ANALYSIS
# =========================================================

def analyze_business(df):

    columns = list(df.columns)

    # -----------------------------------------------------
    # TRUE DUPLICATE COUNT BEFORE REMOVING DUPLICATES
    # -----------------------------------------------------

    duplicate_count = int(df.duplicated().sum())

    # -----------------------------------------------------
    # COLUMN DETECTION
    # -----------------------------------------------------

    sales_column = find_column(
        columns,
        [
            "sales",
            "sale",
            "revenue",
            "amount",
            "income",
            "turnover",
            "value",
            "price"
        ]
    )

    profit_column = find_column(
        columns,
        [
            "profit",
            "net profit",
            "gross profit",
            "earning",
            "earnings"
        ]
    )

    quantity_column = find_column(
        columns,
        [
            "quantity",
            "qty",
            "units",
            "unit"
        ]
    )

    cost_column = find_column(
        columns,
        [
            "cost",
            "expense",
            "expenses"
        ]
    )

    product_column = find_column(
        columns,
        [
            "product",
            "item",
            "product name",
            "item name"
        ]
    )

    category_column = find_column(
        columns,
        [
            "category",
            "segment",
            "type"
        ]
    )

    region_column = find_column(
        columns,
        [
            "region",
            "area",
            "location",
            "city",
            "state",
            "zone"
        ]
    )

    customer_column = find_column(
        columns,
        [
            "customer",
            "client",
            "buyer",
            "customer name"
        ]
    )

    # -----------------------------------------------------
    # DATE DETECTION
    # -----------------------------------------------------

    date_column = None

    for col in columns:

        try:

            converted = pd.to_datetime(
                df[col],
                errors="coerce"
            )

            valid_ratio = converted.notna().mean()

            if valid_ratio > 0.5:

                date_column = col
                break

        except Exception:
            pass

    # -----------------------------------------------------
    # NUMERIC COLUMNS
    # -----------------------------------------------------

    numeric_columns = list(
        df.select_dtypes(include=np.number).columns
    )

    # -----------------------------------------------------
    # FALLBACK REVENUE COLUMN
    # -----------------------------------------------------

    if sales_column is None and numeric_columns:

        sales_column = numeric_columns[0]

    # -----------------------------------------------------
    # NUMERIC SERIES
    # -----------------------------------------------------

    revenue = 0
    profit = 0
    quantity = 0
    cost = 0

    if sales_column:

        revenue = pd.to_numeric(
            df[sales_column],
            errors="coerce"
        ).fillna(0).sum()

    if profit_column:

        profit = pd.to_numeric(
            df[profit_column],
            errors="coerce"
        ).fillna(0).sum()

    elif cost_column and sales_column:

        cost = pd.to_numeric(
            df[cost_column],
            errors="coerce"
        ).fillna(0).sum()

        profit = revenue - cost

    if quantity_column:

        quantity = pd.to_numeric(
            df[quantity_column],
            errors="coerce"
        ).fillna(0).sum()

    # -----------------------------------------------------
    # PROFIT MARGIN
    # -----------------------------------------------------

    margin = 0

    if revenue != 0:
        margin = (profit / revenue) * 100

    # -----------------------------------------------------
    # AVERAGE VALUE
    # -----------------------------------------------------

    average_value = 0

    if len(df) > 0:
        average_value = revenue / len(df)

    # -----------------------------------------------------
    # MISSING VALUES
    # -----------------------------------------------------

    missing_values = int(
        df.isna().sum().sum()
    )

    # -----------------------------------------------------
    # CHARTS
    # -----------------------------------------------------

    charts = []

    # -----------------------------------------------------
    # SALES TREND
    # -----------------------------------------------------

    if date_column and sales_column:

        temp = df.copy()

        temp["_date"] = pd.to_datetime(
            temp[date_column],
            errors="coerce"
        )

        temp["_sales"] = pd.to_numeric(
            temp[sales_column],
            errors="coerce"
        )

        temp = temp.dropna(
            subset=["_date", "_sales"]
        )

        if not temp.empty:

            trend = (
                temp
                .groupby("_date")["_sales"]
                .sum()
                .reset_index()
                .sort_values("_date")
            )

            fig = px.line(
                trend,
                x="_date",
                y="_sales",
                markers=True,
                title="Sales Trend"
            )

            fig.update_layout(
                template="plotly_dark",
                margin=dict(l=20, r=20, t=55, b=20)
            )

            charts.append({
                "title": "Sales Trend",
                "data": chart_json(fig)
            })

    # -----------------------------------------------------
    # PRODUCT / CATEGORY / REGION ANALYSIS
    # -----------------------------------------------------

    group_columns = [
        ("Product Performance", product_column),
        ("Category Performance", category_column),
        ("Regional Performance", region_column)
    ]

    for chart_title, group_column in group_columns:

        if group_column and sales_column:

            temp = df.copy()

            temp["_sales"] = pd.to_numeric(
                temp[sales_column],
                errors="coerce"
            )

            grouped = (
                temp
                .groupby(group_column)["_sales"]
                .sum()
                .reset_index()
                .sort_values(
                    "_sales",
                    ascending=False
                )
                .head(15)
            )

            if not grouped.empty:

                fig = px.bar(
                    grouped,
                    x=group_column,
                    y="_sales",
                    title=chart_title
                )

                fig.update_layout(
                    template="plotly_dark",
                    margin=dict(
                        l=20,
                        r=20,
                        t=55,
                        b=80
                    )
                )

                charts.append({
                    "title": chart_title,
                    "data": chart_json(fig)
                })

    # -----------------------------------------------------
    # SALES DISTRIBUTION
    # -----------------------------------------------------

    if sales_column:

        temp_sales = pd.to_numeric(
            df[sales_column],
            errors="coerce"
        ).dropna()

        if not temp_sales.empty:

            fig = px.histogram(
                temp_sales,
                x=temp_sales,
                nbins=20,
                title="Sales Distribution"
            )

            fig.update_layout(
                template="plotly_dark",
                margin=dict(
                    l=20,
                    r=20,
                    t=55,
                    b=20
                )
            )

            charts.append({
                "title": "Sales Distribution",
                "data": chart_json(fig)
            })

    # -----------------------------------------------------
    # SALES VS PROFIT
    # -----------------------------------------------------

    if sales_column and profit_column:

        temp = df.copy()

        temp["_sales"] = pd.to_numeric(
            temp[sales_column],
            errors="coerce"
        )

        temp["_profit"] = pd.to_numeric(
            temp[profit_column],
            errors="coerce"
        )

        temp = temp.dropna(
            subset=["_sales", "_profit"]
        )

        if not temp.empty:

            fig = px.scatter(
                temp,
                x="_sales",
                y="_profit",
                title="Sales vs Profit",
                trendline="ols"
            )

            fig.update_layout(
                template="plotly_dark",
                margin=dict(
                    l=20,
                    r=20,
                    t=55,
                    b=20
                )
            )

            charts.append({
                "title": "Sales vs Profit",
                "data": chart_json(fig)
            })

    # -----------------------------------------------------
    # PROFIT ANALYSIS
    # -----------------------------------------------------

    if profit_column:

        temp = df.copy()

        temp["_profit"] = pd.to_numeric(
            temp[profit_column],
            errors="coerce"
        )

        if product_column:

            grouped = (
                temp
                .groupby(product_column)["_profit"]
                .sum()
                .reset_index()
                .sort_values(
                    "_profit",
                    ascending=False
                )
                .head(15)
            )

            fig = px.bar(
                grouped,
                x=product_column,
                y="_profit",
                title="Profit by Product"
            )

            fig.update_layout(
                template="plotly_dark"
            )

            charts.append({
                "title": "Profit by Product",
                "data": chart_json(fig)
            })

    # -----------------------------------------------------
    # PIE CHART
    # -----------------------------------------------------

    pie_column = (
        category_column
        or region_column
        or product_column
    )

    if pie_column and sales_column:

        temp = df.copy()

        temp["_sales"] = pd.to_numeric(
            temp[sales_column],
            errors="coerce"
        )

        grouped = (
            temp
            .groupby(pie_column)["_sales"]
            .sum()
            .reset_index()
            .sort_values(
                "_sales",
                ascending=False
            )
            .head(10)
        )

        if not grouped.empty:

            fig = px.pie(
                grouped,
                names=pie_column,
                values="_sales",
                title=f"Sales Distribution by {pie_column}"
            )

            fig.update_layout(
                template="plotly_dark"
            )

            charts.append({
                "title": "Sales Distribution",
                "data": chart_json(fig)
            })

    # =====================================================
    # INSIGHTS
    # =====================================================

    insights = []

    if revenue > 0:

        insights.append(
            f"Total revenue generated from the dataset is {revenue:,.2f}."
        )

    if profit > 0:

        insights.append(
            f"Total profit is {profit:,.2f} with an estimated margin of {margin:.2f}%."
        )

    elif profit < 0:

        insights.append(
            f"The business is currently showing a negative profit of {profit:,.2f}."
        )

    if quantity > 0:

        insights.append(
            f"Total recorded quantity is {quantity:,.0f} units."
        )

    if product_column and sales_column:

        temp = df.copy()

        temp["_sales"] = pd.to_numeric(
            temp[sales_column],
            errors="coerce"
        )

        product_sales = (
            temp
            .groupby(product_column)["_sales"]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        if len(product_sales) > 0:

            best_product = product_sales.index[0]

            insights.append(
                f"Top performing product based on sales is '{best_product}'."
            )

            if len(product_sales) > 1:

                weak_product = product_sales.index[-1]

                insights.append(
                    f"'{weak_product}' is currently one of the weakest products by sales."
                )

    if region_column and sales_column:

        temp = df.copy()

        temp["_sales"] = pd.to_numeric(
            temp[sales_column],
            errors="coerce"
        )

        region_sales = (
            temp
            .groupby(region_column)["_sales"]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        if len(region_sales) > 0:

            best_region = region_sales.index[0]

            insights.append(
                f"The strongest sales region is '{best_region}'."
            )

    if missing_values > 0:

        insights.append(
            f"The dataset contains {missing_values:,} missing values that may affect analysis quality."
        )

    if duplicate_count > 0:

        insights.append(
            f"{duplicate_count:,} duplicate rows were detected."
        )

    # =====================================================
    # GROWTH SUGGESTIONS
    # =====================================================

    suggestions = []

    if margin < 10 and revenue > 0:

        suggestions.append(
            "Review pricing, discounts and operational costs because the profit margin is relatively low."
        )

    if margin >= 20:

        suggestions.append(
            "The business has a healthy margin. Consider scaling the highest-performing products and regions."
        )

    if product_column and sales_column:

        suggestions.append(
            "Focus marketing campaigns and inventory availability on high-performing products."
        )

    if region_column and sales_column:

        suggestions.append(
            "Identify why top regions outperform others and replicate their strategy in weaker regions."
        )

    if quantity > 0:

        suggestions.append(
            "Use quantity and sales together to identify high-volume products and optimize inventory."
        )

    suggestions.append(
        "Use customer segmentation and targeted offers to improve repeat purchases and customer lifetime value."
    )

    suggestions.append(
        "Monitor monthly sales and profit trends to detect growth opportunities and early performance decline."
    )

    # =====================================================
    # STATISTICS
    # =====================================================

    statistics = []

    for col in numeric_columns:

        series = pd.to_numeric(
            df[col],
            errors="coerce"
        ).dropna()

        if len(series) == 0:
            continue

        statistics.append({
            "column": col,
            "mean": round(float(series.mean()), 2),
            "median": round(float(series.median()), 2),
            "min": round(float(series.min()), 2),
            "max": round(float(series.max()), 2),
            "sum": round(float(series.sum()), 2)
        })

    # =====================================================
    # RESULT
    # =====================================================

    result = {

        "kpis": {
            "revenue": round(float(revenue), 2),
            "profit": round(float(profit), 2),
            "margin": round(float(margin), 2),
            "quantity": round(float(quantity), 2),
            "average_value": round(float(average_value), 2),
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
            "missing": missing_values,
            "duplicates": duplicate_count,
            "numeric_columns": len(numeric_columns)
        },

        "detected": {
            "sales_column": sales_column,
            "profit_column": profit_column,
            "quantity_column": quantity_column,
            "cost_column": cost_column,
            "product_column": product_column,
            "category_column": category_column,
            "region_column": region_column,
            "customer_column": customer_column,
            "date_column": date_column
        },

        "charts": charts,

        "insights": insights,

        "suggestions": suggestions,

        "statistics": statistics
    }

    return result


# =========================================================
# PDF REPORT
# =========================================================

def create_pdf_report(result, filename):

    pdf_name = (
        os.path.splitext(filename)[0]
        + "_Business_Analysis_Report.pdf"
    )

    pdf_path = os.path.join(
        REPORT_FOLDER,
        pdf_name
    )

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=35,
        leftMargin=35,
        topMargin=35,
        bottomMargin=35
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=24,
        leading=28,
        alignment=TA_CENTER,
        spaceAfter=8
    )

    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        alignment=TA_CENTER,
        spaceAfter=20
    )

    heading_style = ParagraphStyle(
        "Heading",
        parent=styles["Heading2"],
        fontSize=16,
        leading=20,
        spaceBefore=15,
        spaceAfter=10
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontSize=10,
        leading=15,
        spaceAfter=5
    )

    story = []

    # =====================================================
    # TITLE
    # =====================================================

    story.append(
        Paragraph(
            "PulseBI",
            title_style
        )
    )

    story.append(
        Paragraph(
            "Universal Business Analytics Report",
            subtitle_style
        )
    )

    story.append(
        Paragraph(
            f"<b>Source File:</b> {filename}",
            body_style
        )
    )

    story.append(Spacer(1, 10))

    # =====================================================
    # EXECUTIVE SUMMARY
    # =====================================================

    story.append(
        Paragraph(
            "Executive Summary",
            heading_style
        )
    )

    kpis = result.get("kpis", {})

    kpi_data = [
        ["Business Metric", "Value"],

        [
            "Revenue / Sales",
            f"{kpis.get('revenue', 0):,.2f}"
        ],

        [
            "Profit",
            f"{kpis.get('profit', 0):,.2f}"
        ],

        [
            "Profit Margin",
            f"{kpis.get('margin', 0):.2f}%"
        ],

        [
            "Quantity",
            f"{kpis.get('quantity', 0):,.2f}"
        ],

        [
            "Average Value",
            f"{kpis.get('average_value', 0):,.2f}"
        ],

        [
            "Rows",
            str(kpis.get("rows", 0))
        ],

        [
            "Columns",
            str(kpis.get("columns", 0))
        ]
    ]

    kpi_table = Table(
        kpi_data,
        colWidths=[230, 230]
    )

    kpi_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#111827")
            ),

            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white
            ),

            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold"
            ),

            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),

            (
                "PADDING",
                (0, 0),
                (-1, -1),
                8
            )
        ])
    )

    story.append(kpi_table)

    # =====================================================
    # DETECTED FIELDS
    # =====================================================

    story.append(
        Paragraph(
            "Detected Business Fields",
            heading_style
        )
    )

    detected = result.get(
        "detected",
        {}
    )

    detected_data = [
        ["Business Field", "Detected Column"]
    ]

    for key, value in detected.items():

        detected_data.append([
            key.replace("_", " ").title(),
            str(value)
            if value
            else "Not detected"
        ])

    detected_table = Table(
        detected_data,
        colWidths=[230, 230]
    )

    detected_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#1f2937")
            ),

            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white
            ),

            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),

            (
                "PADDING",
                (0, 0),
                (-1, -1),
                7
            )
        ])
    )

    story.append(detected_table)

    # =====================================================
    # INSIGHTS
    # =====================================================

    story.append(PageBreak())

    story.append(
        Paragraph(
            "Business Insights",
            heading_style
        )
    )

    insights = result.get(
        "insights",
        []
    )

    if insights:

        for insight in insights:

            story.append(
                Paragraph(
                    "• " + str(insight),
                    body_style
                )
            )

    else:

        story.append(
            Paragraph(
                "No major business insights available.",
                body_style
            )
        )

    # =====================================================
    # GROWTH RECOMMENDATIONS
    # =====================================================

    story.append(
        Paragraph(
            "Growth Recommendations",
            heading_style
        )
    )

    suggestions = result.get(
        "suggestions",
        []
    )

    if suggestions:

        for suggestion in suggestions:

            story.append(
                Paragraph(
                    "• " + str(suggestion),
                    body_style
                )
            )

    else:

        story.append(
            Paragraph(
                "No recommendations available.",
                body_style
            )
        )

    # =====================================================
    # DATA HEALTH
    # =====================================================

    story.append(
        Paragraph(
            "Data Health",
            heading_style
        )
    )

    health_data = [
        ["Data Quality Metric", "Value"],

        [
            "Total Rows",
            str(kpis.get("rows", 0))
        ],

        [
            "Total Columns",
            str(kpis.get("columns", 0))
        ],

        [
            "Missing Values",
            str(kpis.get("missing", 0))
        ],

        [
            "Duplicate Rows",
            str(kpis.get("duplicates", 0))
        ],

        [
            "Numeric Fields",
            str(kpis.get("numeric_columns", 0))
        ]
    ]

    health_table = Table(
        health_data,
        colWidths=[230, 230]
    )

    health_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#111827")
            ),

            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white
            ),

            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),

            (
                "PADDING",
                (0, 0),
                (-1, -1),
                7
            )
        ])
    )

    story.append(health_table)

    # =====================================================
    # STATISTICS
    # =====================================================

    statistics = result.get(
        "statistics",
        []
    )

    if statistics:

        story.append(
            Paragraph(
                "Statistical Summary",
                heading_style
            )
        )

        stat_data = [
            [
                "Column",
                "Mean",
                "Median",
                "Min",
                "Max"
            ]
        ]

        for stat in statistics:

            stat_data.append([
                str(stat.get("column", "")),
                str(stat.get("mean", "")),
                str(stat.get("median", "")),
                str(stat.get("min", "")),
                str(stat.get("max", ""))
            ])

        stat_table = Table(
            stat_data,
            repeatRows=1
        )

        stat_table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#111827")
                ),

                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white
                ),

                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.4,
                    colors.grey
                ),

                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8
                ),

                (
                    "PADDING",
                    (0, 0),
                    (-1, -1),
                    5
                )
            ])
        )

        story.append(stat_table)

    # =====================================================
    # FOOTER
    # =====================================================

    story.append(Spacer(1, 25))

    story.append(
        Paragraph(
            "Generated by PulseBI — Universal Business Analytics Platform",
            ParagraphStyle(
                "Footer",
                parent=styles["BodyText"],
                fontSize=8,
                alignment=TA_CENTER
            )
        )
    )

    doc.build(story)

    return pdf_path


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# ANALYZE EXCEL
# =========================================================

@app.route(
    "/analyze",
    methods=["POST"]
)
def analyze():

    if "file" not in request.files:

        return "No file uploaded.", 400

    file = request.files["file"]

    if file.filename == "":

        return "Please select an Excel file.", 400

    # -----------------------------------------------------
    # EXTENSION VALIDATION
    # -----------------------------------------------------

    allowed_extensions = [
        ".xlsx",
        ".xls"
    ]

    extension = os.path.splitext(
        file.filename
    )[1].lower()

    if extension not in allowed_extensions:

        return (
            "Only Excel files (.xlsx / .xls) are supported.",
            400
        )

    # -----------------------------------------------------
    # SAVE FILE
    # -----------------------------------------------------

    filename = file.filename

    file_path = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    file.save(file_path)

    try:

        # -------------------------------------------------
        # READ EXCEL
        # -------------------------------------------------

        excel_file = pd.ExcelFile(
            file_path
        )

        sheet_names = excel_file.sheet_names

        # First sheet
        df = pd.read_excel(
            file_path,
            sheet_name=sheet_names[0]
        )

        # -------------------------------------------------
        # CLEAN
        # -------------------------------------------------

        df = clean_dataframe(df)

        # -------------------------------------------------
        # ANALYZE
        # -------------------------------------------------

        result = analyze_business(df)

        # -------------------------------------------------
        # PREVIEW
        # -------------------------------------------------

        preview = df.head(30).to_html(
            classes="data-table",
            index=False,
            border=0
        )

        # -------------------------------------------------
        # RENDER DASHBOARD
        # -------------------------------------------------

        return render_template(
            "index.html",
            result=result,
            preview=preview,
            filename=filename,
            sheet_names=sheet_names
        )

    except Exception as e:

        return (
            f"""
            <h2>Analysis Error</h2>
            <p>{str(e)}</p>
            <a href="/">Go Back</a>
            """,
            500
        )


# =========================================================
# DOWNLOAD PDF
# =========================================================

@app.route(
    "/download-pdf"
)
def download_pdf():

    filename = request.args.get(
        "filename"
    )

    if not filename:

        return (
            "No analyzed file specified.",
            400
        )

    file_path = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    if not os.path.exists(file_path):

        return (
            "Uploaded Excel file not found.",
            404
        )

    try:

        # -------------------------------------------------
        # READ DATA AGAIN
        # -------------------------------------------------

        df = pd.read_excel(
            file_path
        )

        df = clean_dataframe(
            df
        )

        # -------------------------------------------------
        # ANALYZE
        # -------------------------------------------------

        result = analyze_business(
            df
        )

        # -------------------------------------------------
        # CREATE PDF
        # -------------------------------------------------

        pdf_path = create_pdf_report(
            result,
            filename
        )

        # -------------------------------------------------
        # DOWNLOAD
        # -------------------------------------------------

        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=os.path.basename(
                pdf_path
            ),
            mimetype="application/pdf"
        )

    except Exception as e:

        return (
            f"""
            <h2>PDF Generation Error</h2>
            <p>{str(e)}</p>
            <a href="/">Go Back</a>
            """,
            500
        )


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )