from flask import Flask, render_template, request, redirect, flash, session, send_file # type: ignore
import xml.etree.ElementTree as ET 
import pandas as pd # type: ignore
import openpyxl # type: ignore
from fpdf import FPDF # type: ignore
import os
from datetime import datetime
from openpyxl.styles import Font, PatternFill, Border, Side # type: ignore
import sqlite3
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = 'clave_secreta_para_flask'

# Función para conectar y crear la base de datos
def init_db():
    conn = sqlite3.connect('app.db')  # Nombre del archivo de la base de datos
    cursor = conn.cursor()

    # Crear tabla de usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')

    # Crear tabla de facturas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS facturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detalles TEXT NOT NULL,
            fecha TEXT NOT NULL,
            total REAL NOT NULL
        )
    ''')
    # Crear tabla de reportes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reportes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            fecha TEXT NOT NULL,
            total REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    

# Llamar a la función para crear las tablas al inicio
init_db()

# Conectar a la base de datos SQLite
def get_db_connection():
    conn = sqlite3.connect('app.db')
    conn.row_factory = sqlite3.Row
    return conn


facturas_info = []

#conexion y uso de la base datos 
#login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Obtener el usuario de la base de datos
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM usuarios WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        # Verificar si el usuario existe y si la contraseña es correcta
        if user is None:
            flash("El correo electrónico no está registrado.")
            return redirect('/login')
        elif not check_password_hash(user['password'], password):
            flash("Contraseña incorrecta.")
            return redirect('/login')

        # Guardar el usuario en la sesión
        session['user_id'] = user['id']
        session['user_name'] = user['username']  # Guardar el nombre en la sesión
        flash("Has iniciado sesión correctamente.")
        return redirect('/upload')

    return render_template('login.html')


 # Cerrar sesión
@app.route('/logout')
def logout():
        # Eliminar el usuario de la sesión
        session.pop('user_id', None)
        flash("Has cerrado sesión correctamente.")
        return redirect('/login')

@app.route('/upload')
def destino():
    # Verificar si el usuario está autenticado
    if 'user_id' not in session:
        flash("Debes iniciar sesión para acceder a esta página.")
        return redirect('/login')
    return render_template('upload.html')



#Registro
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Encriptar la contraseña antes de guardarla
        hashed_password = generate_password_hash(password)

        # Guardar en la base de datos
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO usuarios (username, email, password)VALUES (?, ?, ?)'
                         , (username, email, hashed_password))
            conn.commit()
            flash("Registro exitoso. Ya puedes iniciar sesión.")
            return redirect('/registro')
        except sqlite3.IntegrityError:
            flash("El correo electrónico ya está registrado.")
            return redirect('/registro')
        finally:
            conn.close()
            #return redirect('/login')
    
    return render_template('registro.html')

#seccion factura
@app.route('/facturas')
def ver_facturas():
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM facturas')
    facturas = cursor.fetchall()
    conn.close()

    return render_template('facturas.html', facturas=facturas)

@app.route('/crear_factura', methods=['POST'])
def crear_factura():
    detalles = request.form['detalles']
    fecha = request.form['fecha']
    total = request.form['total']

    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO facturas (detalles, fecha, total)
        VALUES (?, ?, ?)
    ''', (detalles, fecha, total))
    conn.commit()
    conn.close()

    return redirect('/facturas')

# Ruta para la página principal
@app.route('/')
def index():
    return render_template('inicio.html')
#Ruta para página de inicio
@app.route('/inicio')
def inicio():
    return render_template('inicio.html')
#Ruta para sección en donde se almacenaran
@app.route('/guardar_reporte', methods=['POST'])
def guardar_reporte():
    nombre = request.form['nombre']
    fecha = request.form['fecha']
    total = request.form['total']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO reportes (nombre, fecha, total)
        VALUES (?, ?, ?)
    ''', (nombre, fecha, total))
    conn.commit()
    conn.close()

    return redirect('/reportes.anteriores')
#Ruta para sección en donde se almacenaran reportes anteriores
@app.route('/reportes.anteriores')
def reportesanteriores():
    # Verificar si el usuario está autenticado
    if 'user_id' not in session:
        flash("Debes iniciar sesión para acceder a esta página.")
        return redirect('/login')

    conn = get_db_connection()
    reportes = conn.execute('SELECT * FROM reportes ORDER BY fecha DESC').fetchall()
    conn.close()
    
    return render_template('reportes.html', reportes=reportes)
# Ruta para subir los archivos XML y generar los reportes
@app.route('/upload', methods=['GET', 'POST'])
def upload_files():
# Verificar si el usuario está autenticado
    global facturas_info  # Declarar facturas_info como global
    uploaded_files = request.files.getlist('xml_files')

    # Reiniciar facturas_info antes de procesar nuevos archivos
    facturas_info = []

    for file in uploaded_files:
        try:
            tree = ET.parse(file)
            root = tree.getroot()

            # Extraer información de la factura (igual que en tu código original)
            estado = root.find('estado').text if root.find('estado') is not None else None
            numero_autorizacion = root.find('numeroAutorizacion').text if root.find('numeroAutorizacion') is not None else None
            fecha_autorizacion = root.find('fechaAutorizacion').text if root.find('fechaAutorizacion') is not None else None
            ambiente = root.find('ambiente').text if root.find('ambiente') is not None else None

            comprobante_element = root.find('comprobante')
            if comprobante_element is not None:
                comprobante_xml = comprobante_element.text.strip()
                if comprobante_xml.startswith('<?xml'):
                    comprobante_xml = comprobante_xml.split('?>', 1)[1].strip()
            else:
                continue

            comprobante_root = ET.fromstring(comprobante_xml)
            info_tributaria = comprobante_root.find('infoTributaria')
            razon_social = info_tributaria.find('razonSocial').text if info_tributaria is not None else None
            ruc = info_tributaria.find('ruc').text if info_tributaria is not None else None
            clave_acceso = info_tributaria.find('claveAcceso').text if info_tributaria is not None else None
            
            codigo_factura = info_tributaria.find('secuencial').text if info_tributaria is not None else None
            info_factura = comprobante_root.find('infoFactura')
            fecha_emision = info_factura.find('fechaEmision').text if info_factura is not None else None
            total_sin_impuestos = info_factura.find('totalSinImpuestos').text if info_factura is not None else None
            importe_total = info_factura.find('importeTotal').text if info_factura is not None else None
            detalles = comprobante_root.find('detalles')

            if detalles is not None:
                productos = detalles.findall('detalle')
                ivas = {"0%": 0, "5%": 0, "12%": 0, "15%": 0}
                total_factura = 0
                for producto in productos:
                    codigo = producto.find('codigoPrincipal').text if producto.find('codigoPrincipal') is not None else None
                    descripcion = producto.find('descripcion').text if producto.find('descripcion') is not None else None
                    cantidad = float(producto.find('cantidad').text) if producto.find('cantidad') is not None else 0.0
                    precio_unitario = float(producto.find('precioUnitario').text) if producto.find('precioUnitario') is not None else 0.0
                    precio_total_sin_impuesto = float(producto.find('precioTotalSinImpuesto').text) if producto.find('precioTotalSinImpuesto') is not None else 0.0

                    impuesto_element = producto.find('impuestos')
                    if impuesto_element is not None:
                        valor_impuesto = impuesto_element.find('impuesto')
                        impuesto = float(valor_impuesto.find('valor').text) if valor_impuesto is not None else 0.0
                        tarifa = float(valor_impuesto.find('tarifa').text) if valor_impuesto.find('tarifa') is not None else 0.0
                    else:
                        impuesto = 0.0
                        tarifa = 0.0
                    total_producto = precio_total_sin_impuesto + impuesto
                    total_factura += total_producto

                    # Determinar el tipo de IVA y sumar al diccionario de IVAs
                    if tarifa == 0:
                        ivas["0%"] += impuesto
                    elif tarifa == 5:
                        ivas["5%"] += impuesto
                    elif tarifa == 12:
                        ivas["12%"] += impuesto
                    elif tarifa == 15:
                        ivas["15%"] += impuesto
                    else:
                        ivas[f"{tarifa}%"] = ivas.get(f"{tarifa}%", 0) + impuesto

            # Crear una cadena con los IVAs de la factura
            ivas_str = ", ".join([f"{k}: ${v:.2f}" for k, v in ivas.items() if v > 0])

            facturas_info.append({
                'Codigo Factura': codigo_factura,
                'Estado de la autorización': estado,
                'Fecha de autorización': fecha_autorizacion,
                'Ambiente': ambiente,
                'Razón Social': razon_social,
                'RUC': ruc,
                'Fecha de Emisión': fecha_emision,
                'Código': codigo,
                'Descripción': descripcion,
                'Cantidad': cantidad,
                'Precio Unitario': precio_unitario,
                'iva 0%': ivas.get("0%", 0),
                'iva 5%': ivas.get("5%", 0),
                'iva 12%': ivas.get("12%", 0),
                'iva 15%': ivas.get("15%", 0),
                'Total sin impuestos': total_sin_impuestos,
                'Total con impuestos': importe_total,
                'Número de autorización': numero_autorizacion,
                'Clave de Acceso': clave_acceso
            })
        except ET.ParseError:
            continue
        except Exception as e:
            print(f"Error: {e}")

    # Generar reporte en Excel
    df_facturas = pd.DataFrame(facturas_info)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo_excel = f'reporte_facturas_{timestamp}.xlsx'
    

    writer = pd.ExcelWriter(archivo_excel, engine='openpyxl')

    # Guardar el DataFrame en Excel
    df_facturas.to_excel(writer, index=False, sheet_name='Reporte')

    # Obtener la hoja de trabajo
    workbook = writer.book
    worksheet = workbook['Reporte']

    # Aplicar formato a la hoja
    for idx, col in enumerate(df_facturas.columns):
        # Establecer el ancho de la columna basado en la longitud máxima en la columna
        max_len = max(df_facturas[col].astype(str).map(len).max(), len(col))
        worksheet.column_dimensions[openpyxl.utils.get_column_letter(idx+1)].width = max_len + 2

    # Aplicar estilo a la fila de encabezados
    for cell in worksheet[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color='87CEEB', end_color='87CEEB', fill_type='solid')

    # Aplicar bordes a todas las celdas
    thin_border = Border(left=Side(style='thin'),
                     right=Side(style='thin'),
                     top=Side(style='thin'),
                     bottom=Side(style='thin'))

    for row in worksheet.iter_rows(min_row=1, max_row=worksheet.max_row, min_col=1, max_col=worksheet.max_column):
        for cell in row:
            cell.border = thin_border

    # Aplicar filtro
    worksheet.auto_filter.ref = worksheet.dimensions

    # Congelar la primera fila
    worksheet.freeze_panes = 'A2'

    # Guardar el archivo
    writer.close()



    # Función para generar el PDF con diseño de factura
    def generar_pdf_facturas(facturas_info): 
        archivo_pdf = f'reporte_facturas_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)

        # Iterar sobre las facturas
        for factura in facturas_info:
            pdf.add_page()  # Agregar una nueva página para cada factura

            # Cabecera con logo e información de la empresa
            pdf.set_font('Arial', 'B', 16)
            pdf.cell(0, 10, 'Systems Ec.', 0, 1, 'C')
            pdf.set_font('Arial', 'I', 12)
            pdf.cell(0, 10, 'RUC: 1234567890001', 0, 1, 'C')
            pdf.cell(0, 10, 'Dirección: Calle Falsa 123, Ciudad', 0, 1, 'C')
            pdf.cell(0, 10, 'Teléfono: (555) 555-5555', 0, 1, 'C')
            pdf.image('descarga.png', x=10, y=8, w=30)  # Añadir un logo a la cabecera
            pdf.ln(15)

            # Título de la factura
            pdf.set_font('Arial', 'B', 14)
            pdf.cell(0, 10, f"Factura N°: {factura['Codigo Factura']}", 0, 1, 'L')
            pdf.ln(5)

            # Información del cliente
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 10, "Información del Cliente:", 0, 1)
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 10, f"Razón Social: {factura['Razón Social']}", 0, 1)
            pdf.cell(0, 10, f"RUC: {factura['RUC']}", 0, 1)
            pdf.cell(0, 10, f"Fecha de Emisión: {factura['Fecha de Emisión']}", 0, 1)
            pdf.ln(5)

            # Sección de detalles de productos (tabla)
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(30, 10, "Código", 1)
            pdf.cell(60, 10, "Descripción", 1)
            pdf.cell(30, 10, "Cantidad", 1)
            pdf.cell(30, 10, "Precio Unitario", 1)
            pdf.cell(40, 10, "Total", 1)
            pdf.ln()

            # Contenido de la tabla de productos
            pdf.set_font('Arial', '', 10)
            pdf.cell(30, 10, str(factura['Código']), 1)
            pdf.cell(60, 10, factura['Descripción'], 1)
            pdf.cell(30, 10, str(factura['Cantidad']), 1)
            pdf.cell(30, 10, f"${factura['Precio Unitario']:.2f}", 1)
            total = factura['Cantidad'] * factura['Precio Unitario']
            pdf.cell(40, 10, f"${total:.2f}", 1)
            pdf.ln(15)

            # Sección de subtotales y totales
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(120)  # Mueve la celda a la derecha para alinear los subtotales
            pdf.cell(30, 10, "Subtotal:", 0)
            pdf.cell(40, 10, f"${float(factura['Total sin impuestos']):.2f}", 0)
            pdf.ln()

            # Detalles de IVA
            for iva, valor in [("IVA 0%", factura['iva 0%']), ("IVA 5%", factura['iva 5%']), ("IVA 12%", factura['iva 12%']), ("IVA 15%", factura['iva 15%'])]:
                pdf.cell(120)  # Alinear los valores de IVA
                pdf.cell(30, 10, f"{iva}:", 0)
                pdf.cell(40, 10, f"${valor:.2f}", 0)
                pdf.ln()

            # Total final
            pdf.cell(120)
            pdf.cell(30, 10, "Total:", 0)
            pdf.cell(40, 10, f"${float(factura['Total con impuestos']):.2f}", 0)
            pdf.ln(10)

        # Guardar el archivo PDF y retornar el nombre del archivo
        pdf.output(archivo_pdf, 'F')
        return archivo_pdf



    # Llamar a la función para generar el PDF
    archivo_pdf = generar_pdf_facturas(facturas_info)

    # Asegúrate de tener el DataFrame df_facturas ya definido antes de esta parte
    # Convertir DataFrame a HTML para previsualización
    tabla_html = df_facturas.to_html(classes='preview-table', index=False)

    # Convertir DataFrame a JSON para pasar a JavaScript
    datos_json = df_facturas.to_json(orient='records')

    # Retornar los archivos generados para su descarga
    return render_template(
        'upload.html',
        excel_report=archivo_excel,
        pdf_report=archivo_pdf,
        tabla_html=tabla_html,
        datos_json=datos_json
    )



# Ruta para descargar el archivo Excel
@app.route('/download_excel')
def download_excel():
    filename = request.args.get('filename')
    custom_name = request.args.get('custom_name')
    if not custom_name.endswith('.xlsx'):
        custom_name += '.xlsx'
    return send_file(filename, as_attachment=True, download_name=custom_name)

# Ruta para descargar el archivo Pdf
@app.route('/download_pdf')
def download_pdf():
    filename = request.args.get('filename')
    custom_name = request.args.get('custom_name')
    if not custom_name.endswith('.pdf'):
        custom_name += '.pdf'
    return send_file(filename, as_attachment=True, download_name=custom_name)

@app.route('/dashboard')
def dashboard():
# Verificar si el usuario está autenticado
    if 'user_id' not in session:
        flash("Debes iniciar sesión para acceder a esta página.")
        return redirect('/login')
    # Procesa los datos de las facturas (asumiendo que tienes acceso a facturas_info)
    total_facturas = len(facturas_info)
    total_ventas = sum(float(factura['Total con impuestos']) for factura in facturas_info)
    ventas_sin_impuestos = sum(float(factura['Total sin impuestos']) for factura in facturas_info)
    promedio_venta = total_ventas / total_facturas if total_facturas > 0 else 0
    
    # Datos para gráficos
    ventas_por_cliente = {}
    
    for factura in facturas_info:
        cliente = factura['Razón Social']
        monto = float(factura['Total con impuestos'])
        ventas_por_cliente[cliente] = ventas_por_cliente.get(cliente, 0) + monto

    iva_totales = {
        'IVA 0%': sum(factura['iva 0%'] for factura in facturas_info),
        'IVA 5%': sum(factura['iva 5%'] for factura in facturas_info),
        'IVA 12%': sum(factura['iva 12%'] for factura in facturas_info),
        'IVA 15%': sum(factura['iva 15%'] for factura in facturas_info)
    }

    return render_template('dashboard.html', 
                           total_facturas=total_facturas,
                           total_ventas=total_ventas,
                           ventas_sin_impuestos=ventas_sin_impuestos,
                           promedio_venta=promedio_venta,
                           ventas_por_cliente=ventas_por_cliente,
                           iva_totales=iva_totales)  

if __name__ == '__main__':
    app.run(debug=True)
