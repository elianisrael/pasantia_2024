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
import struct

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

def update_db():
    """Agrega nuevas columnas a la tabla reportes si no existen."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Agregar la columna tabla_html si no existe
    cursor.execute("PRAGMA table_info(reportes)")
    columns = [col[1] for col in cursor.fetchall()]  # Lista de nombres de columnas

    if "tabla_html" not in columns:
        cursor.execute("ALTER TABLE reportes ADD COLUMN tabla_html TEXT")
        print("Columna 'tabla_html' agregada a la tabla 'reportes'.")

    # Agregar la columna datos_json si no existe
    if "datos_json" not in columns:
        cursor.execute("ALTER TABLE reportes ADD COLUMN datos_json TEXT")
        print("Columna 'datos_json' agregada a la tabla 'reportes'.")

    conn.commit()
    conn.close()

# Llamar a esta función al inicio de la aplicación
update_db()


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
            return redirect('/index')
        elif not check_password_hash(user['password'], password):
            flash("Contraseña incorrecta.")
            return redirect('/index')

        # Guardar el usuario en la sesión
        session['user_id'] = user['id']
        session['user_name'] = user['username']  # Guardar el nombre en la sesión
        session['user_email'] = user['email']    # Guardar el correo en la sesión
        
        flash("Has iniciado sesión correctamente.")
        return redirect('/upload')

    return render_template('index.html')


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
import struct

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

    # Convertir la lista de reportes de sqlite3.Row a diccionarios y modificar los valores de 'total'
    reportes_modificados = []
    for reporte in reportes:
        reporte_dict = dict(reporte)  # Convertir sqlite3.Row a diccionario
        if isinstance(reporte_dict['total'], bytes):
            try:
                # Decodificar bytes a float usando struct
                reporte_dict['total'] = struct.unpack('f', reporte_dict['total'])[0]
            except Exception as e:
                print(f"Error al convertir bytes a float: {e}")
                reporte_dict['total'] = 0.0  # Asignar un valor por defecto en caso de error
        reportes_modificados.append(reporte_dict)

    return render_template('reportes.html', reportes=reportes_modificados, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, nombre=nombre)


@app.route('/upload', methods=['GET', 'POST'])
def upload_files():
    global facturas_info
    facturas_info = []
    productos_info = []

    if 'user_id' not in session:
        flash("Debes iniciar sesión para acceder a esta página.")
        return redirect(url_for('index'))

    uploaded_files = request.files.getlist('xml_files')

    # Dentro de la función upload_files
    for file in uploaded_files:
        try:
            content = file.read().decode('utf-8')
            file.seek(0)

            tree = ET.parse(file)
            root = tree.getroot()

            # Extraer datos del XML
            estado = root.find('estado').text if root.find('estado') is not None else None
            numero_autorizacion = root.find('numeroAutorizacion').text if root.find('numeroAutorizacion') is not None else None
            fecha_autorizacion = root.find('fechaAutorizacion').text if root.find('fechaAutorizacion') is not None else None
            ambiente = root.find('ambiente').text if root.find('ambiente') is not None else None

            # Procesar comprobante y datos de la factura
            comprobante_element = root.find('comprobante')
            if comprobante_element is not None:
                comprobante_xml = comprobante_element.text.strip()
                if comprobante_xml.startswith('<?xml'):
                    comprobante_xml = comprobante_xml.split('?>', 1)[1].strip()

                comprobante_root = ET.fromstring(comprobante_xml)

                # Acceder a infoTributaria y verificar que esté presente
                info_tributaria = comprobante_root.find('infoTributaria')

                if info_tributaria is not None:
                    razon_social = info_tributaria.find('razonSocial').text if info_tributaria.find('razonSocial') is not None else "No especificado"
                    nombre_comercial = info_tributaria.find('nombreComercial').text if info_tributaria.find('nombreComercial') is not None else "No especificado"
                    ruc_vendedor = info_tributaria.find('ruc').text if info_tributaria.find('ruc') is not None else "No especificado"  # Asegúrate que esta línea esté presente
                    clave_acceso = info_tributaria.find('claveAcceso').text if info_tributaria is not None else None
                    codigo_factura = info_tributaria.find('secuencial').text if info_tributaria is not None else None
                else:
                    razon_social = nombre_comercial = ruc_vendedor = clave_acceso = codigo_factura = "No especificado"

                # Acceder a razonSocialComprador
                razon_social_comprador = comprobante_root.find('.//razonSocialComprador').text if comprobante_root.find('.//razonSocialComprador') is not None else "No especificado"

                # Acceder a la información de la factura
                info_factura = comprobante_root.find('infoFactura')
                total_sin_impuestos = info_factura.find('totalSinImpuestos').text if info_factura is not None else 0.0
                importe_total = info_factura.find('importeTotal').text if info_factura is not None else 0.0

                # Agregar datos de factura a la lista
                factura_info = {
                    'Codigo Factura': codigo_factura,
                    'Razón Social comprador': razon_social_comprador,
                    'RUC del Comprador': ruc_vendedor,  # Esto es el 'RUC del Comprador'
                    'Razón Social del Vendedor': razon_social,
                    'Fecha de Emisión': fecha_autorizacion,
                    'Total sin impuestos': float(total_sin_impuestos),  # Agregar esta línea
                    'Total con impuestos': float(importe_total),  # Agregar esta línea
                    'RUC del Vendedor': ruc_vendedor  # Asegurarse de que esta clave esté definida
                }

                facturas_info.append(factura_info)

        except Exception as e:
            print(f"Error procesando el archivo {file.filename}: {str(e)}")

    # Generar la previsualización
    df_facturas = pd.DataFrame(facturas_info)
    tabla_html = df_facturas.to_html(classes='preview-table', index=False)
    datos_json = df_facturas.to_json(orient='records')

    # Generar el PDF
    archivo_pdf = generar_pdf_facturas(facturas_info, productos_info)

    # Generar reporte en Excel
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo_excel = f'reporte_facturas_{timestamp}.xlsx'
    writer = pd.ExcelWriter(archivo_excel, engine='openpyxl')
    df_facturas.to_excel(writer, index=False, sheet_name='Reporte')
    writer.close()

    # Retornar los archivos generados para su descarga
    return render_template(
        'upload.html',
        excel_report=archivo_excel,
        pdf_report=archivo_pdf,
        tabla_html=tabla_html,
        datos_json=datos_json
    )



# Función para generar el PDF con diseño de factura
def generar_pdf_facturas(facturas_info, productos_info=None):
    if productos_info is None:
        productos_info = []

    archivo_pdf = f'reporte_facturas_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    for factura in facturas_info:
        pdf.add_page()

        # Añadir el cuadro principal de información
        pdf.set_xy(10, 10)
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(190, 10, "NO TIENE LOGO", border=1, ln=1, align='C')

        # Cuadro izquierdo: Información del vendedor
        pdf.set_xy(10, 20)
        pdf.set_font('Arial', '', 10)
        pdf.multi_cell(85, 8, f"""
        DEMO SYSTEMSEC
        VESO DERMATOLOGÍA INTEGRAL CIA LTDA
        """, border=1)

        # Cuadro derecho: Información del emisor
        pdf.set_xy(100, 20)
        pdf.multi_cell(100, 8, f"""
        RUC: {factura['RUC del Comprador']}  # Aquí se usa correctamente el RUC del Comprador
        FACTURA: {factura['Codigo Factura']}
        NÚMERO DE AUTORIZACIÓN: {factura['Fecha de Emisión']}
        """, border=1, align='L')

        # Cuadro inferior: Información del comprador
        pdf.set_xy(10, 70)
        pdf.multi_cell(85, 8, f"""
        Razón Social/Nombres: {factura['Razón Social comprador']}
        Identificación: {factura['RUC del Comprador']}
        Fecha: {factura['Fecha de Emisión']}
        """, border=1)

        # Tabla de productos
        pdf.set_xy(10, 130)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(40, 8, "Código", 1)
        pdf.cell(70, 8, "Descripción", 1)
        pdf.cell(20, 8, "Cantidad", 1)
        pdf.cell(30, 8, "P. Unitario", 1)
        pdf.cell(30, 8, "Total", 1, 1)

        pdf.set_font('Arial', '', 10)
        for producto in productos_info:
            pdf.cell(40, 8, str(producto['Código']), 1)
            pdf.cell(70, 8, str(producto['Descripción']), 1)
            pdf.cell(20, 8, str(producto['Cantidad']), 1)
            pdf.cell(30, 8, f"${producto['Precio Unitario']:.2f}", 1)
            pdf.cell(30, 8, f"${producto['Total']:.2f}", 1, 1)

        # Totales
        pdf.ln(5)
        pdf.cell(160, 8, "Subtotal:", 0, 0, 'R')
        pdf.cell(30, 8, f"${factura['Total sin impuestos']:.2f}", 1, 1, 'R')  # Aquí se usa correctamente el total

        for iva_tipo in ['IVA 0%', 'IVA 5%', 'IVA 12%', 'IVA 15%']:
            if iva_tipo in factura and float(factura[iva_tipo]) > 0:
                pdf.cell(160, 8, f"{iva_tipo}:", 0, 0, 'R')
                pdf.cell(30, 8, f"${factura[iva_tipo]:.2f}", 1, 1, 'R')

        pdf.cell(160, 8, "Total con impuestos:", 0, 0, 'R')
        pdf.cell(30, 8, f"${factura['Total con impuestos']:.2f}", 1, 1, 'R')

    pdf.output(archivo_pdf, 'F')
    return archivo_pdf

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
            # Convertir las fechas de inicio y fin en objetos datetime
            fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')

            # Filtrar las facturas basadas en el rango de fechas
            facturas_filtradas = [
                f for f in facturas_filtradas 
                if fecha_inicio_dt <= datetime.strptime(f['Fecha de Emisión'], '%Y-%m-%dT%H:%M:%S%z').date() <= fecha_fin_dt
            ]
        except ValueError:
            flash("Formato de fecha inválido")

    # Análisis temporal
    ventas_por_mes = {}
    for factura in facturas_filtradas:
        fecha = datetime.strptime(factura['Fecha de Emisión'], '%Y-%m-%dT%H:%M:%S%z').date()
        mes_año = fecha.strftime('%Y-%m')
        ventas_por_mes[mes_año] = ventas_por_mes.get(mes_año, 0) + float(factura['Total con impuestos'])


    
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
        fecha = datetime.strptime(factura['Fecha de Emisión'], '%Y-%m-%dT%H:%M:%S%z').date()
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

    # Convertir el reporte en un diccionario mutable
    reporte_dict = dict(reporte)

    # Convertir 'total' a float si es necesario
    try:
        if isinstance(reporte_dict['total'], bytes):
            reporte_dict['total'] = struct.unpack('f', reporte_dict['total'])[0]
    except Exception as e:
        print(f"Error al convertir 'total': {e}")
        reporte_dict['total'] = 0.0  # Asignar valor predeterminado en caso de error

    # Pasar el diccionario modificado a la plantilla
    return render_template(
        'ver_reporte.html', 
        reporte=reporte_dict,  # Usar el diccionario modificado
        tabla_html=reporte_dict['tabla_html'], 
        datos_json=reporte_dict['datos_json']
    )


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

@app.route('/guardar_reporte_con_tabla', methods=['POST'])
def guardar_reporte_con_tabla():
    if 'user_id' not in session:
        flash("Debes iniciar sesión para guardar reportes.")
        return redirect(url_for('index'))

    user_id = session['user_id']
    excel_filename = request.form.get('excel_filename')
    pdf_filename = request.form.get('pdf_filename')
    reporte_nombre = request.form.get('reporte_nombre')
    tabla_html = request.form.get('tabla_html')
    datos_json = request.form.get('datos_json')

    if not excel_filename or not pdf_filename or not reporte_nombre:
        flash("Información incompleta para guardar el reporte.")
        return redirect(url_for('upload'))

    # Calcular el total del reporte
    total = calcular_total_reporte(excel_filename)

    conn = get_db_connection()
    try:
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute('''
            INSERT INTO reportes (user_id, nombre, fecha, total, tabla_html, datos_json) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, reporte_nombre, fecha, total, tabla_html, datos_json))
        conn.commit()
        flash("Reporte guardado exitosamente.")
    except Exception as e:
        print(f"Error al guardar el reporte: {e}")
        flash("Hubo un error al guardar el reporte.")
    finally:
        conn.close()

    return redirect(url_for('reportes_anteriores'))



if __name__ == '__main__':
    app.run(debug=True)
