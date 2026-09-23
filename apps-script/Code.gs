/**
 * Control de Gastos — backend en Google Apps Script.
 *
 * Recibe los gastos que envía el Atajo (Shortcut) del iPhone cada vez que
 * pagas con Apple Pay, junto con tu respuesta a "¿En qué estás gastando?",
 * y los guarda en esta hoja de cálculo.
 *
 * Endpoints (una vez publicado como Aplicación web):
 *   POST  <url>                      -> registra un gasto (JSON)
 *   GET   <url>?accion=categorias    -> lista de categorías (texto, una por línea)
 *   GET   <url>?token=...            -> panel con el resumen del mes
 */

const HOJA_GASTOS = 'Gastos';
const HOJA_CATEGORIAS = 'Categorías';
const HOJA_RESUMEN = 'Resumen';
const SIN_CATEGORIA = 'Sin categoría';

const ENCABEZADOS = ['Fecha', 'Monto', 'Categoría', 'Descripción', 'Comercio', 'Tarjeta', 'Origen'];

const CATEGORIAS_INICIALES = [
  'Comida',
  'Supermercado',
  'Transporte',
  'Casa',
  'Servicios',
  'Salud',
  'Ocio',
  'Ropa',
  'Suscripciones',
  'Educación',
  'Regalos',
  'Otros',
];

/**
 * Ejecuta esta función UNA vez desde el editor (botón ▶ Ejecutar).
 * Crea las hojas, las categorías, el resumen y tu token secreto.
 */
function configurar() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  const gastos = obtenerOCrearHoja_(ss, HOJA_GASTOS);
  if (gastos.getLastRow() === 0) {
    gastos.appendRow(ENCABEZADOS);
    gastos.getRange(1, 1, 1, ENCABEZADOS.length).setFontWeight('bold').setBackground('#e8f0fe');
    gastos.setFrozenRows(1);
    gastos.getRange('A:A').setNumberFormat('dd/mm/yyyy hh:mm');
    gastos.getRange('B:B').setNumberFormat('#,##0.00');
  }

  const categorias = obtenerOCrearHoja_(ss, HOJA_CATEGORIAS);
  if (categorias.getLastRow() === 0) {
    categorias.appendRow(['Categoría']);
    categorias.getRange('A1').setFontWeight('bold').setBackground('#e8f0fe');
    CATEGORIAS_INICIALES.forEach(function (c) { categorias.appendRow([c]); });
    categorias.setFrozenRows(1);
  }

  const resumen = obtenerOCrearHoja_(ss, HOJA_RESUMEN);
  resumen.clear();
  resumen.getRange('A1').setValue('Mes (primer día)').setFontWeight('bold');
  resumen.getRange('B1').setFormula('=DATE(YEAR(TODAY()),MONTH(TODAY()),1)').setNumberFormat('mmmm yyyy');
  resumen.getRange('A2').setValue('Total del mes').setFontWeight('bold');
  resumen.getRange('B2')
    .setFormula("=SUMIFS(Gastos!B:B,Gastos!A:A,\">=\"&B1,Gastos!A:A,\"<\"&EDATE(B1,1))")
    .setNumberFormat('#,##0.00');
  resumen.getRange('A4:B4').setValues([['Categoría', 'Gastado este mes']]).setFontWeight('bold').setBackground('#e8f0fe');
  resumen.getRange('A5').setFormula("=FILTER('Categorías'!A2:A,'Categorías'!A2:A<>\"\")");
  resumen.getRange('B5').setFormula(
    "=ARRAYFORMULA(IF(A5:A=\"\",,SUMIFS(Gastos!B:B,Gastos!C:C,A5:A,Gastos!A:A,\">=\"&B1,Gastos!A:A,\"<\"&EDATE(B1,1))))"
  );
  resumen.getRange('B5:B').setNumberFormat('#,##0.00');
  resumen.autoResizeColumns(1, 2);

  const props = PropertiesService.getScriptProperties();
  let token = props.getProperty('TOKEN');
  if (!token) {
    token = Utilities.getUuid().replace(/-/g, '').slice(0, 16);
    props.setProperty('TOKEN', token);
  }

  Logger.log('✅ Listo. Tu token secreto es: ' + token);
  Logger.log('Guárdalo: lo vas a pegar en el Atajo del iPhone.');
}

/** Muestra el token en el registro por si lo perdiste. */
function verToken() {
  Logger.log(PropertiesService.getScriptProperties().getProperty('TOKEN'));
}

/**
 * Registra un gasto. Cuerpo JSON esperado:
 * {
 *   "token": "...",            (obligatorio)
 *   "monto": "$1.234,50",      (obligatorio; acepta texto con símbolo de moneda)
 *   "categoria": "Comida",     (lo que elegiste en el Atajo)
 *   "descripcion": "Almuerzo", (tu respuesta a "¿En qué estás gastando?")
 *   "comercio": "Starbucks",   (lo aporta Apple Pay)
 *   "tarjeta": "Visa",         (lo aporta Apple Pay)
 *   "origen": "Apple Pay"      (opcional: "Apple Pay", "Manual", ...)
 * }
 */
function doPost(e) {
  try {
    const datos = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (!tokenValido_(datos.token)) {
      return responder_({ ok: false, error: 'Token inválido' });
    }

    const monto = parsearMonto_(datos.monto);
    if (monto === null) {
      return responder_({ ok: false, error: 'Monto inválido: ' + datos.monto });
    }

    const categoria = normalizarCategoria_(datos.categoria);
    const fila = [
      new Date(),
      monto,
      categoria,
      limpiar_(datos.descripcion),
      limpiar_(datos.comercio),
      limpiar_(datos.tarjeta),
      limpiar_(datos.origen) || 'Apple Pay',
    ];

    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    try {
      SpreadsheetApp.getActiveSpreadsheet().getSheetByName(HOJA_GASTOS).appendRow(fila);
    } finally {
      lock.releaseLock();
    }

    const totalCategoria = totalMesCategoria_(categoria);
    return responder_({
      ok: true,
      mensaje: 'Guardado: ' + formatear_(monto) + ' en ' + categoria +
        '. Este mes llevas ' + formatear_(totalCategoria) + ' en ' + categoria + '.',
    });
  } catch (err) {
    return responder_({ ok: false, error: String(err) });
  }
}

function doGet(e) {
  const params = (e && e.parameter) || {};

  // El Atajo usa esto para armar el menú "¿En qué categoría?".
  if (params.accion === 'categorias') {
    return ContentService.createTextOutput(listarCategorias_().join('\n'))
      .setMimeType(ContentService.MimeType.TEXT);
  }

  if (!tokenValido_(params.token)) {
    return HtmlService.createHtmlOutput('<p style="font-family:sans-serif">Falta el token. Abre esta URL con <code>?token=TU_TOKEN</code>.</p>');
  }

  const plantilla = HtmlService.createTemplateFromFile('Panel');
  plantilla.datos = datosPanel_();
  return plantilla.evaluate()
    .setTitle('Control de Gastos')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------

function obtenerOCrearHoja_(ss, nombre) {
  return ss.getSheetByName(nombre) || ss.insertSheet(nombre);
}

function tokenValido_(token) {
  const esperado = PropertiesService.getScriptProperties().getProperty('TOKEN');
  return Boolean(esperado) && String(token || '').trim() === esperado;
}

function responder_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function limpiar_(valor) {
  return valor === undefined || valor === null ? '' : String(valor).trim();
}

/**
 * Convierte "$1.234,50", "1,234.50", "€ 12,5", "12.50 USD" o 12.5 en número.
 * El último separador ("," o ".") se toma como decimal si le siguen 1 o 2 dígitos.
 */
function parsearMonto_(valor) {
  if (typeof valor === 'number') return isFinite(valor) ? Math.abs(valor) : null;
  let texto = limpiar_(valor).replace(/[^\d.,-]/g, '');
  if (!texto) return null;

  const ultimo = Math.max(texto.lastIndexOf(','), texto.lastIndexOf('.'));
  if (ultimo !== -1 && /^\d{1,2}$/.test(texto.slice(ultimo + 1))) {
    const entero = texto.slice(0, ultimo).replace(/[.,]/g, '');
    texto = entero + '.' + texto.slice(ultimo + 1);
  } else {
    texto = texto.replace(/[.,]/g, '');
  }

  const numero = Math.abs(parseFloat(texto));
  return isFinite(numero) ? numero : null;
}

function listarCategorias_() {
  const hoja = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(HOJA_CATEGORIAS);
  if (!hoja || hoja.getLastRow() < 2) return CATEGORIAS_INICIALES.slice();
  return hoja.getRange(2, 1, hoja.getLastRow() - 1, 1).getValues()
    .map(function (r) { return limpiar_(r[0]); })
    .filter(String);
}

/** Acepta la categoría sin importar mayúsculas; si no existe, la agrega. */
function normalizarCategoria_(valor) {
  const texto = limpiar_(valor);
  if (!texto) return SIN_CATEGORIA;
  const existentes = listarCategorias_();
  const encontrada = existentes.find(function (c) { return c.toLowerCase() === texto.toLowerCase(); });
  if (encontrada) return encontrada;
  SpreadsheetApp.getActiveSpreadsheet().getSheetByName(HOJA_CATEGORIAS).appendRow([texto]);
  return texto;
}

function gastosDelMes_() {
  const hoja = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(HOJA_GASTOS);
  if (hoja.getLastRow() < 2) return [];
  const hoy = new Date();
  const inicio = new Date(hoy.getFullYear(), hoy.getMonth(), 1);
  return hoja.getRange(2, 1, hoja.getLastRow() - 1, ENCABEZADOS.length).getValues()
    .filter(function (r) { return r[0] instanceof Date && r[0] >= inicio; });
}

function totalMesCategoria_(categoria) {
  return gastosDelMes_()
    .filter(function (r) { return r[2] === categoria; })
    .reduce(function (suma, r) { return suma + Number(r[1] || 0); }, 0);
}

function datosPanel_() {
  const filas = gastosDelMes_();
  const porCategoria = {};
  let total = 0;
  filas.forEach(function (r) {
    const monto = Number(r[1] || 0);
    total += monto;
    porCategoria[r[2]] = (porCategoria[r[2]] || 0) + monto;
  });

  const categorias = Object.keys(porCategoria)
    .map(function (c) { return { nombre: c, total: porCategoria[c] }; })
    .sort(function (a, b) { return b.total - a.total; });

  const zona = Session.getScriptTimeZone();
  const ultimos = filas.slice(-10).reverse().map(function (r) {
    return {
      fecha: Utilities.formatDate(r[0], zona, 'dd/MM HH:mm'),
      monto: Number(r[1] || 0),
      categoria: r[2],
      descripcion: r[3] || r[4] || '',
    };
  });

  return {
    mes: Utilities.formatDate(new Date(), zona, 'MMMM yyyy'),
    total: total,
    categorias: categorias,
    ultimos: ultimos,
  };
}

function formatear_(n) {
  return '$' + Number(n).toFixed(2);
}
