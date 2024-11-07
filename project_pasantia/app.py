from flask import Flask, render_template, request, redirect, flash, session, send_file, url_for # type: ignore
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
import json

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
            user_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            fecha TEXT NOT NULL,
            total REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES usuarios (id)
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
        session['user_email'] = user['email']    # Guardar el correo en la sesión
        
        flash("Has iniciado sesión correctamente.")
        return redirect('/upload')

    return render_template('login.html')


 # Cerrar sesión
@app.route('/logout')
def logout():
        # Eliminar el usuario de la sesión
        session.pop('user_id', None)
        flash("Has cerrado sesión correctamente.")
        return redirect('/index')

@app.route('/index')
def destino():

    return render_template('index.html')



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
def home():
    return redirect('/index')  # Redirige a la página de login

@app.route('/upload')
def upload():
    return render_template('upload.html')

#Ruta para página de inicio
#@app.route('/inicio')
#def inicio():
 #   return render_template('inicio.html')

#Ruta para sección en donde se almacenaran
@app.route('/guardar_reporte', methods=['POST'])
def guardar_reporte():
    if 'user_id' not in session:
        flash("Debes iniciar sesión para guardar reportes.")
        return redirect(url_for('index'))

    user_id = session['user_id']
    excel_filename = request.form.get('excel_filename')
    pdf_filename = request.form.get('pdf_filename')
    reporte_nombre = request.form.get('reporte_nombre')

    if not excel_filename or not pdf_filename or not reporte_nombre:
        flash("Información incompleta para guardar el reporte.")
        return redirect(url_for('upload'))

    # Calcular el total del reporte
    total = calcular_total_reporte(excel_filename)

    conn = get_db_connection()
    try:
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute('''
            INSERT INTO reportes (user_id, nombre, fecha, total) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, reporte_nombre, fecha, total))
        conn.commit()
        flash("Reporte guardado exitosamente.")
    except Exception as e:
        print(f"Error al guardar el reporte: {e}")
        flash("Hubo un error al guardar el reporte.")
    finally:
        conn.close()

    return redirect(url_for('reportes_anteriores'))

def calcular_total_reporte(excel_filename):
    try:
        df = pd.read_excel(excel_filename)
        total = df['Total con impuestos'].sum()  # Asegúrate de que esta columna exista en tu Excel
        return total
    except Exception as e:
        print(f"Error al calcular el total del reporte: {e}")
        return 0
#Ruta para sección en donde se almacenaran reportes anteriores
@app.route('/reportes.anteriores')
def reportes_anteriores():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    nombre = request.args.get('nombre', '')
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')

    conn = get_db_connection()
    query = '''SELECT * FROM reportes WHERE user_id = ?'''
    params = [user_id]

    if nombre:
        query += ' AND nombre LIKE ?'
        params.append(f"%{nombre}%")
    if fecha_inicio and fecha_fin:
        query += ' AND fecha BETWEEN ? AND ?'
        params.extend([fecha_inicio, fecha_fin])

    query += ' ORDER BY fecha DESC'
    reportes = conn.execute(query, params).fetchall()
    conn.close()

    return render_template('reportes.html', reportes=reportes, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, nombre=nombre)


# Ruta para subir los archivos XML y generar los reportes
@app.route('/upload', methods=['GET', 'POST'])
def upload_files():
    print("Iniciando proceso de carga de archivos")
    
    # Verificar si el usuario está autenticado
    if 'user_id' not in session:
        print("Usuario no autenticado")
        flash("Debes iniciar sesión para acceder a esta página.")
        return redirect(url_for('index'))

    uploaded_files = request.files.getlist('xml_files')
    print(f"Número de archivos cargados: {len(uploaded_files)}")

    # Reiniciar facturas_info antes de procesar nuevos archivos
    global facturas_info
    facturas_info = []
    productos_info = []

    for file in uploaded_files:
        print(f"\nProcesando archivo: {file.filename}")
        try:
            # Leer el contenido del archivo para depuración
            content = file.read().decode('utf-8')
            print(f"Contenido del archivo {file.filename}:\n{content[:200]}...")  # Primeros 200 caracteres
            file.seek(0)  # Regresar al inicio del archivo

            tree = ET.parse(file)
            root = tree.getroot()
            print("XML parseado correctamente")

            # Extraer información básica de la autorización
            estado = root.find('estado').text if root.find('estado') is not None else None
            numero_autorizacion = root.find('numeroAutorizacion').text if root.find('numeroAutorizacion') is not None else None
            fecha_autorizacion = root.find('fechaAutorizacion').text if root.find('fechaAutorizacion') is not None else None
            ambiente = root.find('ambiente').text if root.find('ambiente') is not None else None

            print(f"Estado: {estado}")
            print(f"Número de autorización: {numero_autorizacion}")

            # Procesar el comprobante
            comprobante_element = root.find('comprobante')
            if comprobante_element is not None:
                comprobante_xml = comprobante_element.text.strip()
                if comprobante_xml.startswith('<?xml'):
                    comprobante_xml = comprobante_xml.split('?>', 1)[1].strip()
                print("Elemento comprobante encontrado y procesado")
            else:
                print(f"El archivo {file.filename} no contiene un elemento 'comprobante'")
                continue

            comprobante_root = ET.fromstring(comprobante_xml)
            print("Comprobante XML parseado correctamente")

            # Información tributaria
            info_tributaria = comprobante_root.find('infoTributaria')
            razon_social = info_tributaria.find('razonSocial').text if info_tributaria.find('razonSocial') is not None else "No especificado"
            nombre_comercial = info_tributaria.find('nombreComercial').text if info_tributaria.find('nombreComercial') is not None else "No especificado"
            ruc_vendedor = info_tributaria.find('ruc').text if info_tributaria is not None else None
            clave_acceso = info_tributaria.find('claveAcceso').text if info_tributaria is not None else None
            codigo_factura = info_tributaria.find('secuencial').text if info_tributaria is not None else None

            print(f"Información tributaria procesada - RUC: {ruc_vendedor}")

            # Información de la factura
            info_factura = comprobante_root.find('infoFactura')
            fecha_emision = info_factura.find('fechaEmision').text if info_factura is not None else None
            total_sin_impuestos = info_factura.find('totalSinImpuestos').text if info_factura is not None else None
            importe_total = info_factura.find('importeTotal').text if info_factura is not None else None

            # Información del comprador
            razon_social_comprador = comprobante_root.find('.//razonSocialComprador').text if comprobante_root.find('.//razonSocialComprador') is not None else "No especificado"
            ruc_comprador = comprobante_root.find('.//identificacionComprador').text if comprobante_root.find('.//identificacionComprador') is not None else "No especificado"

            print(f"Información de factura procesada - Fecha: {fecha_emision}")

            # Procesar detalles y productos
            detalles = comprobante_root.find('detalles')
            if detalles is not None:
                print("Procesando detalles de productos")
                productos = detalles.findall('detalle')
                ivas = {"0%": 0, "5%": 0, "12%": 0, "15%": 0}
                total_factura = 0

                for producto in productos:
                    codigo = producto.find('codigoPrincipal').text if producto.find('codigoPrincipal') is not None else None
                    descripcion = producto.find('descripcion').text if producto.find('descripcion') is not None else None
                    cantidad = float(producto.find('cantidad').text) if producto.find('cantidad') is not None else 0.0
                    precio_unitario = float(producto.find('precioUnitario').text) if producto.find('precioUnitario') is not None else 0.0
                    precio_total_sin_impuesto = float(producto.find('precioTotalSinImpuesto').text) if producto.find('precioTotalSinImpuesto') is not None else 0.0

                    # Procesar impuestos del producto
                    impuesto_element = producto.find('impuestos/impuesto')
                    if impuesto_element is not None:
                        impuesto = float(impuesto_element.find('valor').text) if impuesto_element.find('valor') is not None else 0.0
                        tarifa = float(impuesto_element.find('tarifa').text) if impuesto_element.find('tarifa') is not None else 0.0
                        
                        # Sumar al IVA correspondiente
                        if tarifa == 0:
                            ivas["0%"] += impuesto
                        elif tarifa == 5:
                            ivas["5%"] += impuesto
                        elif tarifa == 12:
                            ivas["12%"] += impuesto
                        elif tarifa == 15:
                            ivas["15%"] += impuesto
                    else:
                        impuesto = 0.0
                        tarifa = 0.0

                    total_producto = precio_total_sin_impuesto + impuesto
                    total_factura += total_producto

                    productos_info.append({
                        'Codigo Factura': codigo_factura,
                        'Código': codigo,
                        'Descripción': descripcion,
                        'Cantidad': cantidad,
                        'Precio Unitario': precio_unitario,
                        'Precio Total Sin Impuesto': precio_total_sin_impuesto,
                        'IVA': impuesto,
                        'Total': total_producto
                    })
                    print(f"Producto procesado: {codigo} - {descripcion}")

            # Agregar información de la factura
            factura_info = {
                'Codigo Factura': codigo_factura,
                'Estado de la autorización': estado,
                'Fecha de autorización': fecha_autorizacion,
                'Ambiente': ambiente,
                'Razón Social comprador': razon_social_comprador,
                'RUC del Comprador': ruc_comprador,
                'Razón Social del Vendedor': razon_social,
                'Nombre Comercial del Vendedor': nombre_comercial,
                'RUC del Vendedor': ruc_vendedor,
                'Fecha de Emisión': fecha_emision,
                'IVA 0%': ivas["0%"],
                'IVA 5%': ivas["5%"],
                'IVA 12%': ivas["12%"],
                'IVA 15%': ivas["15%"],
                'Total sin impuestos': total_sin_impuestos,
                'Total con impuestos': importe_total,
                'Número de autorización': numero_autorizacion,
                'Clave de Acceso': clave_acceso
            }
            facturas_info.append(factura_info)
            print(f"Factura procesada: {codigo_factura} - {razon_social_comprador}")

        except ET.ParseError:
            print(f"Error al analizar el archivo {file.filename}: El archivo no es un XML válido.")
        except Exception as e:
            print(f"Error procesando el archivo {file.filename}: {str(e)}")

    print(f"Total de facturas procesadas: {len(facturas_info)}")
    print(f"Total de productos procesados: {len(productos_info)}")


    # Generar reporte en Excel
    df_facturas = pd.DataFrame(facturas_info)
    df_productos = pd.DataFrame(productos_info)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo_excel = f'reporte_facturas_{timestamp}.xlsx'
    

    writer = pd.ExcelWriter(archivo_excel, engine='openpyxl')

    # Guardar el DataFrame en Excel
    df_facturas.to_excel(writer, index=False, sheet_name='Reporte')
    df_productos.to_excel(writer, sheet_name='Productos', index=False)

    # Obtener la hoja de trabajo
    workbook = writer.book
    worksheet_facturas = workbook['Reporte']
    worksheet_productos = workbook['Productos']

    # Aplicar formato a la hoja
    for idx, col in enumerate(df_facturas.columns):
        # Establecer el ancho de la columna basado en la longitud máxima en la columna
        max_len = max(df_facturas[col].astype(str).map(len).max(), len(col))
        worksheet_facturas.column_dimensions[openpyxl.utils.get_column_letter(idx+1)].width = max_len + 2

    for idx, col in enumerate(df_productos.columns):
        # Establecer el ancho de la columna basado en la longitud máxima en la columna
        max_len = max(df_productos[col].astype(str).map(len).max(), len(col))
        worksheet_productos.column_dimensions[openpyxl.utils.get_column_letter(idx+1)].width = max_len + 2
    
    for worksheet in [worksheet_facturas, worksheet_productos]:
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
    def generar_pdf_facturas(facturas_info, productos_info=None): 
        if productos_info is None:
            productos_info = []
        
        print(f"Total de facturas: {len(facturas_info)}")
        print(f"Total de productos: {len(productos_info)}")

        archivo_pdf = f'reporte_facturas_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)

        for factura in facturas_info:
            pdf.add_page()

            # Cabecera de la empresa (vendedor)
            pdf.set_font('Arial', 'B', 16)
            pdf.cell(0, 10, factura['Nombre Comercial del Vendedor'], 0, 1, 'C')
            pdf.set_font('Arial', 'I', 12)
            pdf.cell(0, 10, f"Razón Social: {factura['Razón Social del Vendedor']}", 0, 1, 'C')
            pdf.cell(0, 10, f"RUC: {factura['RUC del Vendedor']}", 0, 1, 'C')
            pdf.cell(0, 10, 'Dirección: Calle Falsa 123, Ciudad', 0, 1, 'C')
            pdf.cell(0, 10, 'Teléfono: (555) 555-5555', 0, 1, 'C')
            pdf.image('descarga.png', x=10, y=8, w=30)
            pdf.ln(15)

            # Información de la factura
            pdf.set_font('Arial', 'B', 14)
            codigo_factura = factura['Codigo Factura']
            pdf.cell(0, 10, f"Factura N°: {codigo_factura}", 0, 1, 'L')
            pdf.ln(5)

            # Información del cliente (comprador)
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 10, "Información del Cliente:", 0, 1)
            pdf.set_font('Arial', '', 10)
            # Usar las claves correctas que coinciden con factura_info
            pdf.cell(0, 10, f"Razón Social del Comprador: {factura['Razón Social comprador']}", 0, 1)
            pdf.cell(0, 10, f"RUC del Comprador: {factura['RUC del Comprador']}", 0, 1)
            pdf.cell(0, 10, f"Fecha de Emisión: {factura['Fecha de Emisión']}", 0, 1)
            pdf.ln(5)

            # Tabla de productos
            pdf.set_font('Arial', 'B', 12)
            w_codigo = 30
            w_descripcion = 60
            w_cantidad = 25
            w_precio = 35
            w_total = 40
            h = 10

            # Encabezados de la tabla
            pdf.cell(w_codigo, h, "Código", 1)
            pdf.cell(w_descripcion, h, "Descripción", 1)
            pdf.cell(w_cantidad, h, "Cantidad", 1)
            pdf.cell(w_precio, h, "P. Unitario", 1)
            pdf.cell(w_total, h, "Total", 1)
            pdf.ln()

            # Filtrar y mostrar productos de esta factura
            productos_factura = [p for p in productos_info if p['Codigo Factura'] == codigo_factura]
            print(f"Productos encontrados para factura {codigo_factura}: {len(productos_factura)}")

            # Contenido de la tabla
            pdf.set_font('Arial', '', 10)
            subtotal = 0
            for producto in productos_factura:
                codigo = str(producto['Código'])
                descripcion = str(producto['Descripción'])
                if len(descripcion) > 25:
                    descripcion = descripcion[:22] + '...'
                
                cantidad = str(producto['Cantidad'])
                precio_unitario = producto['Precio Unitario']
                total_producto = producto['Total']
                subtotal += total_producto

                pdf.cell(w_codigo, h, codigo, 1)
                pdf.cell(w_descripcion, h, descripcion, 1)
                pdf.cell(w_cantidad, h, cantidad, 1)
                pdf.cell(w_precio, h, f"${precio_unitario:.2f}", 1)
                pdf.cell(w_total, h, f"${total_producto:.2f}", 1)
                pdf.ln()

            pdf.ln(5)

            # Sección de totales
            pdf.set_font('Arial', 'B', 12)
            x_position = 120
            
            pdf.cell(x_position)
            pdf.cell(30, 10, "Subtotal:", 0)
            pdf.cell(40, 10, f"${float(factura['Total sin impuestos']):.2f}", 0)
            pdf.ln()

            # IVAs
            for iva_tipo in ['IVA 0%', 'IVA 5%', 'IVA 12%', 'IVA 15%']:
                if factura[iva_tipo] > 0:
                    pdf.cell(x_position)
                    pdf.cell(30, 10, f"{iva_tipo}:", 0)
                    pdf.cell(40, 10, f"${factura[iva_tipo]:.2f}", 0)
                    pdf.ln()

            # Total final
            pdf.set_font('Arial', 'B', 14)
            pdf.cell(x_position)
            pdf.cell(30, 10, "TOTAL:", 0)
            pdf.cell(40, 10, f"${float(factura['Total con impuestos']):.2f}", 0)
            pdf.ln(15)

            # Información adicional
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 10, f"Número de Autorización: {factura['Número de autorización']}", 0, 1)
            pdf.cell(0, 10, f"Fecha de Autorización: {factura['Fecha de autorización']}", 0, 1)
            pdf.cell(0, 10, f"Ambiente: {factura['Ambiente']}", 0, 1)
            pdf.cell(0, 10, f"Estado de Autorización: {factura['Estado de la autorización']}", 0, 1)

        pdf.output(archivo_pdf, 'F')
        return archivo_pdf

    # Llamar a la función para generar el PDF
    archivo_pdf = generar_pdf_facturas(facturas_info, productos_info)

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
    if 'user_id' not in session:
        flash("Debes iniciar sesión para acceder a esta página.")
        return redirect('/index')
    
    # Obtener parámetros de filtro de la URL
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    clientes_filtro = request.args.getlist('clientes[]')
    vendedores_filtro = request.args.getlist('vendedores[]')
    rango_monto = request.args.get('rango_monto')
    
    # Filtrar facturas según los parámetros
    facturas_filtradas = facturas_info.copy()
    
    # Aplicar filtro de fechas
    if fecha_inicio and fecha_fin:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
            facturas_filtradas = [
                f for f in facturas_filtradas 
                if fecha_inicio_dt <= datetime.strptime(f['Fecha de Emisión'], '%d/%m/%Y') <= fecha_fin_dt
            ]
        except ValueError:
            flash("Formato de fecha inválido")
    
    # Aplicar filtro de clientes por RUC
    if clientes_filtro:
        facturas_filtradas = [
            f for f in facturas_filtradas
            if f['RUC del Comprador'] in clientes_filtro
        ]

    # Aplicar filtro de vendedores por RUC
    if vendedores_filtro:
        facturas_filtradas = [
            f for f in facturas_filtradas
            if f['RUC del Vendedor'] in vendedores_filtro
        ]

    # Obtener lista única de RUCs de clientes y sus nombres
    clientes_unicos = sorted(list(set(f['RUC del Comprador'] for f in facturas_info)))
    clientes_nombres = {f['RUC del Comprador']: f['Razón Social comprador'] for f in facturas_info}

    # Obtener lista única de RUCs de vendedores y sus nombres
    vendedores_unicos = sorted(list(set(f['RUC del Vendedor'] for f in facturas_info)))
    vendedores_nombres = {f['RUC del Vendedor']: f['Razón Social del Vendedor'] for f in facturas_info}

    
    # Aplicar filtro de rango de monto
    if rango_monto:
        try:
            min_monto, max_monto = map(float, rango_monto.split('-'))
            facturas_filtradas = [
                f for f in facturas_filtradas 
                if min_monto <= float(f['Total con impuestos']) <= max_monto
            ]
        except ValueError:
            flash("Rango de monto inválido")

    # Procesar datos filtrados
    total_facturas = len(facturas_filtradas)
    total_ventas = sum(float(f['Total con impuestos']) for f in facturas_filtradas)
    ventas_sin_impuestos = sum(float(f['Total sin impuestos']) for f in facturas_filtradas)
    promedio_venta = total_ventas / total_facturas if total_facturas > 0 else 0

    # Análisis por vendedor
    ventas_por_vendedor = {}
    for factura in facturas_filtradas:
        vendedor = factura.get('Razón Social del Vendedor', 'Vendedor no especificado')
        monto = float(factura['Total con impuestos'])
        ventas_por_vendedor[vendedor] = ventas_por_vendedor.get(vendedor, 0) + monto

    # Análisis por cliente
    ventas_por_cliente = {}
    for factura in facturas_filtradas:
        cliente = factura.get('Razón Social comprador', 'Cliente no especificado')
        monto = float(factura['Total con impuestos'])
        ventas_por_cliente[cliente] = ventas_por_cliente.get(cliente, 0) + monto

    # Análisis de IVA
    iva_totales = {
        'IVA 0%': sum(f.get('IVA 0%', 0) for f in facturas_filtradas),
        'IVA 5%': sum(f.get('IVA 5%', 0) for f in facturas_filtradas),
        'IVA 12%': sum(f.get('IVA 12%', 0) for f in facturas_filtradas),
        'IVA 15%': sum(f.get('IVA 15%', 0) for f in facturas_filtradas)
    }

    # Análisis temporal
    ventas_por_mes = {}
    for factura in facturas_filtradas:
        fecha = datetime.strptime(factura['Fecha de Emisión'], '%d/%m/%Y')
        mes_año = fecha.strftime('%Y-%m')
        ventas_por_mes[mes_año] = ventas_por_mes.get(mes_año, 0) + float(factura['Total con impuestos'])


    return render_template('dashboard.html',
                         total_facturas=total_facturas,
                         total_ventas=total_ventas,
                         ventas_sin_impuestos=ventas_sin_impuestos,
                         promedio_venta=promedio_venta,
                         ventas_por_cliente=ventas_por_cliente,
                         ventas_por_vendedor=ventas_por_vendedor,
                         iva_totales=iva_totales,
                         ventas_por_mes=ventas_por_mes,
                         clientes_unicos=clientes_unicos,
                         vendedores_unicos=vendedores_unicos,
                         clientes_nombres=clientes_nombres,
                         vendedores_nombres=vendedores_nombres,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin,
                         clientes_filtro=clientes_filtro,
                         vendedores_filtro=vendedores_filtro,
                         rango_monto=rango_monto)

@app.route('/reporte/<int:id>')
def ver_reporte(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    reporte = conn.execute('SELECT * FROM reportes WHERE id = ?', (id,)).fetchone()
    conn.close()

    if reporte is None:
        flash("Reporte no encontrado.")
        return redirect(url_for('reportes_anteriores'))
    
    return render_template('ver_reporte.html', reporte=reporte)

@app.route('/borrar-reportes', methods=['POST'])
def borrar_reportes():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    reportes_ids = request.json.get('ids', [])
    if reportes_ids:
        conn = get_db_connection()
        conn.executemany('DELETE FROM reportes WHERE id = ?', [(id,) for id in reportes_ids])
        conn.commit()
        conn.close()
    
    return '', 204

@app.route('/borrar-reporte/<int:id>', methods=['DELETE'])
def borrar_reporte(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    conn.execute('DELETE FROM reportes WHERE id = ?', (id,))
    conn.commit()
    conn.close()

    return '', 204


if __name__ == '__main__':
    app.run(debug=True)
