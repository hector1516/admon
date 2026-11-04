"""
pdf_storage.py - Guardado automático de PDFs en share SMB (versión Admon).

Usa smbclient (CLI) para subir archivos directamente al share de red.
Lee la configuración de HUB_Config a través de la conexión de Admon.
"""
import os
import subprocess
import datetime

MESES = {
    1: "01 Enero", 2: "02 Febrero", 3: "03 Marzo",
    4: "04 Abril", 5: "05 Mayo", 6: "06 Junio",
    7: "07 Julio", 8: "08 Agosto", 9: "09 Septiembre",
    10: "10 Octubre", 11: "11 Noviembre", 12: "12 Diciembre"
}

MODULOS = {
    "materiales": "Cotizaciones_Materiales",
}

_PDF_STORAGE_KEYS = ['smb_share_path', 'smb_user', 'smb_password', 'smb_domain', 'pdf_output_dir']


def _get_connection():
    """Obtiene conexión a la BD usando la misma lógica que Admon."""
    from api import main as _m
    return _m.get_connection()


def get_pdf_storage_config():
    """Devuelve dict con la configuración de guardado de PDFs desde HUB_Config."""
    try:
        conn = _get_connection()
        cursor = conn.cursor(as_dict=True)
        placeholders = ', '.join(['%s'] * len(_PDF_STORAGE_KEYS))
        cursor.execute(f"SELECT Clave, Valor FROM HUB_Config WHERE Clave IN ({placeholders})", tuple(_PDF_STORAGE_KEYS))
        rows = cursor.fetchall()
        cfg = {row['Clave']: (row['Valor'] or '').strip() for row in rows}
        conn.close()
        return {k: cfg.get(k, '') for k in _PDF_STORAGE_KEYS}
    except Exception as e:
        print(f"Error reading pdf storage config: {e}")
        return {k: '' for k in _PDF_STORAGE_KEYS}


def _get_smb_config():
    """Obtiene la configuración SMB desde HUB_Config."""
    try:
        cfg = get_pdf_storage_config()
        share_path = cfg.get('smb_share_path', '').strip()
        if share_path.startswith('\\\\'):
            parts = share_path[2:].split('\\', 1)
            server = parts[0]
            share = parts[1] if len(parts) > 1 else ''
        else:
            server = ''
            share = ''
        return {
            'server': server,
            'share': share,
            'user': cfg.get('smb_user', ''),
            'password': cfg.get('smb_password', ''),
            'full_share': f"//{server}/{share}" if server and share else '',
        }
    except Exception:
        return {}


def _smb_run(commands):
    """Ejecuta comandos smbclient. commands: lista de strings. Retorna (stdout, stderr, returncode)."""
    cfg = _get_smb_config()
    if not cfg.get('full_share'):
        return '', 'No SMB config', 1
    cmd_str = '; '.join(commands)
    password = cfg['password'].replace("'", "'\\''")
    shell_cmd = f"smbclient '{cfg['full_share']}' -U '{cfg['user']}%{password}' -c '{cmd_str}'"
    try:
        result = subprocess.run(shell_cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return '', 'Timeout', 1
    except Exception as e:
        return '', str(e), 1


def _build_smb_dir(modulo, fecha):
    """Construye la ruta de directorio en el share."""
    nombre_modulo = MODULOS.get(modulo, modulo)
    if isinstance(fecha, str):
        try:
            fecha = datetime.datetime.strptime(fecha[:10], "%Y-%m-%d").date()
        except ValueError:
            try:
                fecha = datetime.datetime.strptime(fecha[:10], "%d/%m/%Y").date()
            except ValueError:
                fecha = datetime.date.today()
    if isinstance(fecha, datetime.datetime):
        fecha = fecha.date()
    if not isinstance(fecha, datetime.date):
        fecha = datetime.date.today()
    year = fecha.year
    mes_folder = MESES.get(fecha.month, f"{fecha.month:02d} Mes")
    return f"{nombre_modulo}/{year}/{mes_folder}"


def _smb_makedirs(dir_path):
    """Crea carpetas en el share SMB (ignora si ya existen)."""
    parts = dir_path.split('/')
    cmds = []
    current = ''
    for part in parts:
        current = f"{current}/{part}" if current else part
        cmds.append(f'mkdir {current} 2>/dev/null')
    _smb_run(cmds)


def _smb_file_exists(filepath):
    """Verifica si un archivo existe en el share SMB."""
    parts = filepath.rsplit('/', 1)
    if len(parts) != 2:
        return False
    dir_path, filename = parts
    stdout, _, rc = _smb_run([f'cd {dir_path}', 'ls'])
    if rc != 0:
        return False
    return filename in stdout


def _smb_upload(filepath, pdf_bytes):
    """Sube bytes a un archivo en el share SMB usando cd + put."""
    import tempfile
    cfg = _get_smb_config()
    if not cfg.get('full_share'):
        return False
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        parts = filepath.rsplit('/', 1)
        if len(parts) == 2:
            dir_path, filename = parts
            _smb_makedirs(dir_path)
            stdout, stderr, rc = _smb_run([f'cd {dir_path}', f'put {tmp_path} {filename}'])
        else:
            stdout, stderr, rc = _smb_run([f'put {tmp_path} {filepath}'])
        if rc != 0:
            print(f"SMB upload error: {stderr or stdout}")
            return False
        return True
    except Exception as e:
        print(f"SMB upload error: {e}")
        return False
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def pdf_exists(modulo, folio, fecha):
    """Verifica si un PDF ya existe en el share SMB."""
    if not fecha:
        fecha = datetime.date.today()
    dir_path = _build_smb_dir(modulo, fecha)
    filename = f"{folio}.pdf"
    return _smb_file_exists(f"{dir_path}/{filename}")


def save_pdf(modulo, folio, pdf_bytes, fecha):
    """
    Guarda el PDF en el share SMB.
    Retorna la ruta del archivo guardado, o "" si no está configurado.
    """
    if not pdf_bytes:
        return ''
    if not fecha:
        fecha = datetime.date.today()
    # Normalizar fecha a date
    if isinstance(fecha, str):
        try:
            fecha = datetime.datetime.strptime(fecha[:10], "%Y-%m-%d").date()
        except ValueError:
            try:
                fecha = datetime.datetime.strptime(fecha[:10], "%d/%m/%Y").date()
            except ValueError:
                fecha = datetime.date.today()
    if isinstance(fecha, datetime.datetime):
        fecha = fecha.date()
    cfg = _get_smb_config()
    if not cfg.get('full_share'):
        return ''
    dir_path = _build_smb_dir(modulo, fecha)
    filepath = f"{dir_path}/{folio}.pdf"
    try:
        _smb_makedirs(dir_path)
        if _smb_upload(filepath, pdf_bytes):
            return filepath
        return ''
    except Exception as e:
        print(f"Error saving PDF via SMB: {e}")
        return ''
