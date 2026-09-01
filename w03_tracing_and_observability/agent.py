"""Agente de atencion al cliente de un banco (datos mockeados).

Pensado para el workshop de tracing: las tools estan disenadas para que el
agente tenga que encadenar llamados segun la intencion del usuario y segun lo
que va encontrando, no porque el prompt le imponga un orden fijo.

Tres decisiones de diseno que conviene entender antes de leer el codigo:

1. El agente NUNCA recibe ni pasa el customer_id. El harness lo siembra en el
   estado de la sesion cuando el usuario ya esta logueado en la app, y cada tool
   lo lee desde `tool_context`, que ADK inyecta y excluye del schema que ve el
   modelo.

2. Las reglas de negocio (umbrales de bonificacion, que acciones estan
   permitidas, plazos) viven en las tools, nunca en el prompt. El LLM orquesta,
   las tools deciden. Si los umbrales estuvieran tambien en la instruction
   habria dos fuentes de verdad y el modelo a veces calcularia por su cuenta.

3. Minimizacion de datos: ninguna tool devuelve cuanto gana el cliente ni cuanto
   tiene invertido. Devuelven la decision (a que paquetes accede) y el requisito
   publicado de cada paquete. Todo lo que una tool devuelve entra al prompt del
   siguiente call_llm y queda escrito en el trace, asi que el trace es tambien
   una superficie de PII.
"""

import datetime
import uuid

from google.adk.agents.llm_agent import Agent
from google.adk.tools.tool_context import ToolContext


# --- Reglas de negocio (NO van en el prompt) -------------------------------

# Haberes mensuales minimos para bonificar cada paquete, acreditando el sueldo
# en el banco.
_MIN_HABERES = {
    "basico": 1_000_000,
    "silver": 2_000_000,
    "gold": 3_000_000,
    "black": 4_000_000,
}

# Alternativa para quien no acredita haberes: promedio de inversiones de los
# ultimos 6 meses. Requiere cuenta comitente abierta Y encuesta de perfil de
# inversor completada (sin encuesta no se puede operar, asi que no hay promedio).
_MIN_INVERSIONES = {
    "basico": 1_500_000,
    "silver": 2_500_000,
    "gold": 3_500_000,
    "black": 4_500_000,
}

_COSTO_MENSUAL_SIN_BONIFICAR = {
    "basico": 9_500,
    "silver": 18_500,
    "gold": 31_000,
    "black": 52_000,
}

_MARCAS_POR_PAQUETE = {
    "basico": ["visa"],
    "silver": ["visa", "mastercard"],
    "gold": ["visa", "mastercard"],
    "black": ["visa", "mastercard", "amex"],
}

_ORDEN_PAQUETES = ["basico", "silver", "gold", "black"]

_DIAS_HABILES_ENTREGA_PLASTICOS = 10
_MAX_DIAS_PROMESA_DE_PAGO = 30


# --- Datos mock del cliente -----------------------------------------------

# `haberes_mensuales` e `inversiones_promedio_6m` son insumos privados: se usan
# para decidir dentro de las tools y NO se devuelven nunca.
_CUSTOMERS = {
    "cust_1042": {
        "nombre": "Roman",
        "cliente_desde": "2019-03-14",
        "acredita_haberes": False,
        "haberes_mensuales": 0,
        "inversiones_promedio_6m": 0,
        "paquete_tarjetas": "silver",
        "comitente": {"estado": "no_solicitada", "encuesta_inversor": "no_completada"},
        "cuentas": [
            {"tipo": "caja_de_ahorro_pesos", "moneda": "ARS", "alias": "roman.ahorro"},
            {"tipo": "caja_de_ahorro_dolares", "moneda": "USD", "alias": "roman.usd"},
        ],
        "tarjetas": [
            {"marca": "visa", "ultimos_cuatro": "4831", "estado": "activa"},
            {"marca": "mastercard", "ultimos_cuatro": "9002", "estado": "activa"},
        ],
        "en_gestion_judicial": False,
    },
}

_RESUMENES = {
    ("cust_1042", "visa"): {
        "periodo": "2026-07",
        "saldo_pesos": 412_300.55,
        "saldo_dolares": 89.90,
        "pago_minimo_pesos": 61_845.08,
        "vencimiento": "2026-08-05",
        "estado": "vencido_impago",
    },
    ("cust_1042", "mastercard"): {
        "periodo": "2026-07",
        "saldo_pesos": 0.0,
        "saldo_dolares": 0.0,
        "pago_minimo_pesos": 0.0,
        "vencimiento": "2026-08-12",
        "estado": "sin_consumos",
    },
}

_PRESTAMOS = {
    "cust_1042": [
        {
            "producto": "Prestamo personal preaprobado",
            "monto_maximo_pesos": 8_000_000,
            "cuotas": 48,
            "cuota_estimada_pesos": 412_900,
            "tna": "72,50%",
            "cft_con_iva": "119,80%",
            "vigencia_oferta": "2026-08-31",
        },
        {
            "producto": "Adelanto de sueldo",
            "monto_maximo_pesos": 0,
            "cuotas": 0,
            "cuota_estimada_pesos": 0,
            "tna": "-",
            "cft_con_iva": "-",
            "vigencia_oferta": "-",
            "no_disponible_porque": "requiere acreditacion de haberes en el banco",
        },
    ],
}

# Operaciones preparadas y todavia no confirmadas. En un sistema real esto vive
# en el backend, nunca en el prompt.
_OPERACIONES_PENDIENTES = {}


# --- Helpers internos ------------------------------------------------------

def _customer(tool_context: ToolContext) -> dict:
    """Resuelve el cliente logueado desde el estado de la sesion.

    El harness siembra `customer_id` al crear la sesion. El default existe solo
    para poder probar el agente con `adk web`; en produccion no deberia haberlo.
    """
    customer_id = tool_context.state.get("customer_id", "cust_1042")
    return _CUSTOMERS[customer_id]


def _maximo_paquete_bonificable(customer: dict) -> str:
    """Unica implementacion de la regla de bonificacion.

    Hoy: gana la via que mas convenga. Si acredita haberes se evalua por sueldo;
    si ademas puede operar en comitente, se evalua tambien por inversiones y se
    toma el mejor resultado. Cambiar esta funcion es cambiar la regla.
    """
    candidatos = [None]

    if customer["acredita_haberes"]:
        haberes = customer["haberes_mensuales"]
        candidatos += [p for p in _ORDEN_PAQUETES if haberes >= _MIN_HABERES[p]]

    # La via inversiones exige comitente abierta y encuesta completada: sin
    # encuesta el cliente no puede operar, por lo tanto no hay promedio valido.
    comitente = customer["comitente"]
    if comitente["estado"] == "abierta" and comitente["encuesta_inversor"] == "completada":
        promedio = customer["inversiones_promedio_6m"]
        candidatos += [p for p in _ORDEN_PAQUETES if promedio >= _MIN_INVERSIONES[p]]

    alcanzados = [p for p in candidatos if p is not None]
    if not alcanzados:
        return ""
    return max(alcanzados, key=_ORDEN_PAQUETES.index)


def _pesos(monto: int) -> str:
    return f"${monto:,.0f}".replace(",", ".")


def _requisito_publico(paquete: str) -> str:
    """Texto del requisito publicado del paquete. No revela datos del cliente."""
    return (
        f"acreditar haberes por {_pesos(_MIN_HABERES[paquete])} mensuales, "
        f"o mantener inversiones por un promedio de {_pesos(_MIN_INVERSIONES[paquete])} "
        "en los ultimos 6 meses con cuenta comitente operativa"
    )


def _fecha_habil_futura(dias_habiles: int) -> str:
    """Calcula una fecha habil concreta en el backend.

    El LLM no debe calcular dias habiles: no conoce los feriados.
    """
    fecha = datetime.date.today()
    sumados = 0
    while sumados < dias_habiles:
        fecha += datetime.timedelta(days=1)
        if fecha.weekday() < 5:
            sumados += 1
    return fecha.isoformat()


def _nueva_operacion(kind: str, payload: dict) -> str:
    operation_id = f"op_{uuid.uuid4().hex[:8]}"
    _OPERACIONES_PENDIENTES[operation_id] = {"kind": kind, **payload}
    return operation_id


def _tomar_operacion(operation_id: str, kind: str):
    """Consume una operacion pendiente. Garantiza que no se ejecute dos veces."""
    operacion = _OPERACIONES_PENDIENTES.get(operation_id)
    if operacion is None:
        return None, {
            "status": "error",
            "reason": (
                f"La operacion '{operation_id}' no existe o ya fue ejecutada. "
                "Volve a solicitarla antes de confirmar."
            ),
        }
    if operacion["kind"] != kind:
        return None, {
            "status": "error",
            "reason": f"La operacion '{operation_id}' no corresponde a esta confirmacion.",
        }
    return _OPERACIONES_PENDIENTES.pop(operation_id), None


# --- Tools de lectura ------------------------------------------------------

def get_customer_profile(tool_context: ToolContext) -> dict:
    """Devuelve el perfil del cliente logueado.

    Incluye si acredita sus haberes en el banco, dato que sirve para saber que
    gestiones ofrecerle. NO devuelve montos de ingresos ni de inversiones.

    Ejemplo de retorno:
        {"status": "success", "nombre": "Roman", "cliente_desde": "2019-03-14",
         "acredita_haberes": false}
    """
    customer = _customer(tool_context)
    return {
        "status": "success",
        "nombre": customer["nombre"],
        "cliente_desde": customer["cliente_desde"],
        "acredita_haberes": customer["acredita_haberes"],
    }


def get_products(tool_context: ToolContext) -> dict:
    """Lista los productos del cliente: cuentas, cuenta comitente y tarjetas.

    Sirve para resolver referencias ambiguas del usuario ("mi tarjeta", "mi
    cuenta en dolares") y para saber que marcas de tarjeta tiene emitidas.

    El estado de la comitente puede ser "no_solicitada", "solicitada",
    "abierta"; y la encuesta de perfil de inversor "no_completada" o
    "completada". Sin encuesta completada el cliente no puede comprar acciones.

    Ejemplo de retorno:
        {"status": "success",
         "paquete_tarjetas": "silver",
         "cuentas": [{"tipo": "caja_de_ahorro_pesos", "moneda": "ARS", "alias": "roman.ahorro"}],
         "cuenta_comitente": {"estado": "no_solicitada", "encuesta_inversor": "no_completada"},
         "tarjetas": [{"marca": "visa", "ultimos_cuatro": "4831", "estado": "activa"}]}
    """
    customer = _customer(tool_context)
    return {
        "status": "success",
        "paquete_tarjetas": customer["paquete_tarjetas"],
        "cuentas": customer["cuentas"],
        "cuenta_comitente": customer["comitente"],
        "tarjetas": customer["tarjetas"],
    }


def get_package_options(tool_context: ToolContext) -> dict:
    """Dice a que paquetes de tarjetas accede el cliente y cual queda bonificado.

    Esta tool aplica las reglas de bonificacion del banco y devuelve el
    resultado ya decidido. Por privacidad NO devuelve los ingresos ni las
    inversiones del cliente: para los paquetes que hoy no bonifica, devuelve el
    requisito publicado del paquete para que el cliente lo evalue.

    Usar esta tool siempre que el usuario pregunte por bonificaciones, upgrades
    o por que le cobran el paquete. No deducir la elegibilidad por otros medios.

    Ejemplo de retorno:
        {"status": "success",
         "paquete_actual": "silver",
         "bonificado_actualmente": false,
         "costo_mensual_actual": 18500,
         "maximo_paquete_bonificable": null,
         "paquetes": [
           {"paquete": "gold", "bonificado": false, "costo_mensual_si_no_bonifica": 31000,
            "requisito_publicado": "acreditar haberes por $3.000.000 mensuales, o ..."}
         ],
         "notas": ["El cliente no acredita haberes en el banco."]}
    """
    customer = _customer(tool_context)
    actual = customer["paquete_tarjetas"]
    maximo = _maximo_paquete_bonificable(customer)

    def bonificado(paquete: str) -> bool:
        if not maximo:
            return False
        return _ORDEN_PAQUETES.index(paquete) <= _ORDEN_PAQUETES.index(maximo)

    paquetes = [
        {
            "paquete": paquete,
            "bonificado": bonificado(paquete),
            "costo_mensual_si_no_bonifica": _COSTO_MENSUAL_SIN_BONIFICAR[paquete],
            "requisito_publicado": _requisito_publico(paquete),
            "marcas_incluidas": _MARCAS_POR_PAQUETE[paquete],
        }
        for paquete in _ORDEN_PAQUETES
    ]

    notas = []
    if not customer["acredita_haberes"]:
        notas.append(
            "El cliente no acredita haberes en el banco, por lo que la via de "
            "bonificacion disponible es la de inversiones."
        )
    comitente = customer["comitente"]
    if comitente["estado"] != "abierta":
        notas.append(
            "La via de inversiones requiere cuenta comitente abierta; el cliente "
            "todavia no la tiene."
        )
    elif comitente["encuesta_inversor"] != "completada":
        notas.append(
            "La cuenta comitente esta abierta pero la encuesta de perfil de "
            "inversor esta pendiente, y sin ella no se computan inversiones."
        )

    return {
        "status": "success",
        "paquete_actual": actual,
        "bonificado_actualmente": bonificado(actual),
        "costo_mensual_actual": (
            0 if bonificado(actual) else _COSTO_MENSUAL_SIN_BONIFICAR[actual]
        ),
        "maximo_paquete_bonificable": maximo or None,
        "paquetes": paquetes,
        "notas": notas,
    }


def get_card_statement(marca: str, tool_context: ToolContext) -> dict:
    """Devuelve el resumen de la tarjeta de la marca indicada.

    `marca` debe ser una de "visa", "mastercard" o "amex", y el cliente debe
    tener esa marca emitida. Si no la tiene, devuelve status "error" con la
    lista de marcas disponibles: en ese caso reintentar con una de esas.

    Devuelve saldo en pesos y en dolares por separado. No sumar ni convertir las
    monedas: informarlas tal como vienen.

    Ejemplo de retorno:
        {"status": "success", "marca": "visa", "ultimos_cuatro": "4831",
         "periodo": "2026-07", "saldo_pesos": 412300.55, "saldo_dolares": 89.9,
         "pago_minimo_pesos": 61845.08, "vencimiento": "2026-08-05",
         "estado": "vencido_impago"}
    """
    customer = _customer(tool_context)
    marca = marca.lower().strip()
    emitidas = {t["marca"]: t for t in customer["tarjetas"]}

    if marca not in emitidas:
        return {
            "status": "error",
            "reason": f"El cliente no tiene una tarjeta {marca}.",
            "marcas_disponibles": sorted(emitidas),
        }

    customer_id = tool_context.state.get("customer_id", "cust_1042")
    resumen = _RESUMENES.get((customer_id, marca))
    if resumen is None:
        return {
            "status": "error",
            "reason": f"No hay resumenes emitidos para la tarjeta {marca}.",
        }

    return {
        "status": "success",
        "marca": marca,
        "ultimos_cuatro": emitidas[marca]["ultimos_cuatro"],
        **resumen,
    }


def get_available_loans(tool_context: ToolContext) -> dict:
    """Lista los prestamos preaprobados para el cliente.

    Las ofertas vienen ya calculadas por el banco, con TNA y CFT. Informarlas
    exactamente como vienen: no calcular cuotas, no estimar totales y no
    reformular las tasas.

    Ejemplo de retorno:
        {"status": "success", "ofertas": [
          {"producto": "Prestamo personal preaprobado", "monto_maximo_pesos": 8000000,
           "cuotas": 48, "cuota_estimada_pesos": 412900, "tna": "72,50%",
           "cft_con_iva": "119,80%", "vigencia_oferta": "2026-08-31"}]}
    """
    customer_id = tool_context.state.get("customer_id", "cust_1042")
    return {"status": "success", "ofertas": _PRESTAMOS.get(customer_id, [])}


# --- Tools de escritura: solicitar -> confirmar ----------------------------

def request_package_upgrade(paquete_destino: str, tool_context: ToolContext) -> dict:
    """Prepara (NO ejecuta) el cambio de paquete de tarjetas.

    Devuelve un `operation_id` junto con los efectos y el costo mensual. Hay que
    mostrarle al usuario ese resumen, esperar su confirmacion explicita y solo
    entonces llamar a `confirm_package_upgrade` con el `operation_id`.

    El upgrade a un paquete que no queda bonificado esta permitido: en ese caso
    el cliente paga el costo mensual, y hay que decirselo antes de confirmar.

    Ejemplo de retorno:
        {"status": "success", "operation_id": "op_9f21ab03",
         "resumen": "Cambiar el paquete de silver a gold",
         "queda_bonificado": false, "costo_mensual": 31000,
         "efectos": ["Se emiten nuevas tarjetas visa, mastercard"],
         "requiere_confirmacion": true}
    """
    customer = _customer(tool_context)
    destino = paquete_destino.lower().strip()

    if destino not in _ORDEN_PAQUETES:
        return {
            "status": "error",
            "reason": f"Paquete desconocido: '{paquete_destino}'.",
            "paquetes_validos": _ORDEN_PAQUETES,
        }

    actual = customer["paquete_tarjetas"]
    if destino == actual:
        return {"status": "error", "reason": f"El cliente ya tiene el paquete {actual}."}

    maximo = _maximo_paquete_bonificable(customer)
    queda_bonificado = bool(maximo) and (
        _ORDEN_PAQUETES.index(destino) <= _ORDEN_PAQUETES.index(maximo)
    )

    operation_id = _nueva_operacion(
        "package_upgrade", {"paquete_destino": destino, "paquete_origen": actual}
    )
    return {
        "status": "success",
        "operation_id": operation_id,
        "resumen": f"Cambiar el paquete de tarjetas de {actual} a {destino}",
        "queda_bonificado": queda_bonificado,
        "costo_mensual": 0 if queda_bonificado else _COSTO_MENSUAL_SIN_BONIFICAR[destino],
        "efectos": [
            f"Se emiten nuevas tarjetas: {', '.join(_MARCAS_POR_PAQUETE[destino])}",
            "Las tarjetas actuales siguen operativas hasta recibir las nuevas",
        ],
        "requiere_confirmacion": True,
    }


def confirm_package_upgrade(operation_id: str, tool_context: ToolContext) -> dict:
    """Ejecuta un cambio de paquete ya preparado y confirmado por el usuario.

    Solo llamar despues de que el usuario acepto explicitamente. El
    `operation_id` se consume: un segundo intento devuelve error en lugar de
    emitir tarjetas duplicadas.

    Ejemplo de retorno:
        {"status": "success", "numero_de_caso": "CASO-4471",
         "paquete_nuevo": "gold", "entrega_estimada": "2026-08-24",
         "mensaje": "Las tarjetas se entregan por correo en 10 dias habiles."}
    """
    operacion, error = _tomar_operacion(operation_id, "package_upgrade")
    if error:
        return error

    customer = _customer(tool_context)
    customer["paquete_tarjetas"] = operacion["paquete_destino"]
    customer["tarjetas"] = [
        {
            "marca": marca,
            "ultimos_cuatro": next(
                (t["ultimos_cuatro"] for t in customer["tarjetas"] if t["marca"] == marca),
                "0000",
            ),
            "estado": "en_emision",
        }
        for marca in _MARCAS_POR_PAQUETE[operacion["paquete_destino"]]
    ]

    return {
        "status": "success",
        "numero_de_caso": f"CASO-{uuid.uuid4().int % 10000:04d}",
        "paquete_nuevo": operacion["paquete_destino"],
        "entrega_estimada": _fecha_habil_futura(_DIAS_HABILES_ENTREGA_PLASTICOS),
        "mensaje": (
            f"Las tarjetas se entregan por correo dentro de los "
            f"{_DIAS_HABILES_ENTREGA_PLASTICOS} dias habiles."
        ),
    }


def request_investment_account(tool_context: ToolContext) -> dict:
    """Prepara (NO ejecuta) la apertura de la cuenta comitente.

    La cuenta comitente permite comprar acciones y habilita la via de
    bonificacion por inversiones. Devuelve un `operation_id` para confirmar con
    `confirm_investment_account`.

    Importante: el agente puede abrir la cuenta, pero NO puede completar la
    encuesta de perfil de inversor. Esa encuesta es obligatoria para operar y el
    usuario debe completarla el mismo desde el menu de la app.

    Ejemplo de retorno:
        {"status": "success", "operation_id": "op_3c7f19aa",
         "resumen": "Solicitar apertura de cuenta comitente",
         "pasos_posteriores_a_cargo_del_usuario": ["Completar la encuesta de perfil de inversor desde el menu"],
         "requiere_confirmacion": true}
    """
    customer = _customer(tool_context)
    estado = customer["comitente"]["estado"]

    if estado == "abierta":
        return {
            "status": "error",
            "reason": "El cliente ya tiene la cuenta comitente abierta.",
            "encuesta_inversor": customer["comitente"]["encuesta_inversor"],
        }
    if estado == "solicitada":
        return {
            "status": "error",
            "reason": "Ya hay una solicitud de apertura en curso.",
        }

    operation_id = _nueva_operacion("investment_account", {})
    return {
        "status": "success",
        "operation_id": operation_id,
        "resumen": "Solicitar la apertura de una cuenta comitente",
        "efectos": ["Habilita la compra y venta de acciones una vez completada la encuesta"],
        "pasos_posteriores_a_cargo_del_usuario": [
            "Completar la encuesta de perfil de inversor desde el menu de la app. "
            "Es obligatoria y no puede completarla el asistente."
        ],
        "requiere_confirmacion": True,
    }


def confirm_investment_account(operation_id: str, tool_context: ToolContext) -> dict:
    """Ejecuta la apertura de cuenta comitente ya confirmada por el usuario.

    Al terminar hay que recordarle al usuario que todavia debe completar la
    encuesta de perfil de inversor desde el menu para poder operar.

    Ejemplo de retorno:
        {"status": "success", "numero_de_caso": "CASO-8820", "estado": "abierta",
         "encuesta_inversor": "no_completada",
         "pendiente_del_usuario": "Completar la encuesta de perfil de inversor desde el menu."}
    """
    _, error = _tomar_operacion(operation_id, "investment_account")
    if error:
        return error

    customer = _customer(tool_context)
    customer["comitente"]["estado"] = "abierta"

    return {
        "status": "success",
        "numero_de_caso": f"CASO-{uuid.uuid4().int % 10000:04d}",
        "estado": "abierta",
        "encuesta_inversor": customer["comitente"]["encuesta_inversor"],
        "pendiente_del_usuario": (
            "Completar la encuesta de perfil de inversor desde el menu de la app. "
            "Hasta entonces no se pueden comprar acciones ni computar inversiones."
        ),
    }


def request_payment_promise(marca: str, fecha_de_pago: str, tool_context: ToolContext) -> dict:
    """Prepara (NO ejecuta) una promesa de pago para una tarjeta vencida e impaga.

    Solo aplica si el resumen esta en estado "vencido_impago". `fecha_de_pago`
    va en formato YYYY-MM-DD y no puede exceder los 30 dias desde hoy. Devuelve
    un `operation_id` para confirmar con `confirm_payment_promise`.

    Los intereses siguen devengandose hasta el pago efectivo: hay que
    informarselo al usuario antes de confirmar.

    Ejemplo de retorno:
        {"status": "success", "operation_id": "op_5ab20c31",
         "resumen": "Promesa de pago de la tarjeta visa terminada en 4831 para el 2026-08-20",
         "saldo_pesos": 412300.55, "saldo_dolares": 89.9,
         "advertencias": ["Los intereses se siguen devengando hasta el pago efectivo."],
         "requiere_confirmacion": true}
    """
    customer = _customer(tool_context)

    if customer["en_gestion_judicial"]:
        return {
            "status": "error",
            "reason": (
                "La deuda esta en gestion judicial: el asistente no puede acordar "
                "pagos. Derivar a un representante."
            ),
        }

    resumen = get_card_statement(marca, tool_context)
    if resumen["status"] != "success":
        return resumen

    if resumen["estado"] != "vencido_impago":
        return {
            "status": "error",
            "reason": (
                f"La tarjeta {resumen['marca']} no esta vencida e impaga "
                f"(estado actual: {resumen['estado']}), no corresponde una promesa de pago."
            ),
        }

    try:
        fecha = datetime.date.fromisoformat(fecha_de_pago)
    except ValueError:
        return {
            "status": "error",
            "reason": f"Fecha invalida: '{fecha_de_pago}'. Usar formato YYYY-MM-DD.",
        }

    hoy = datetime.date.today()
    if fecha < hoy:
        return {"status": "error", "reason": "La fecha de pago no puede estar en el pasado."}

    limite = hoy + datetime.timedelta(days=_MAX_DIAS_PROMESA_DE_PAGO)
    if fecha > limite:
        return {
            "status": "error",
            "reason": (
                f"La fecha excede el maximo permitido de {_MAX_DIAS_PROMESA_DE_PAGO} dias. "
                f"La ultima fecha posible es {limite.isoformat()}."
            ),
        }

    operation_id = _nueva_operacion(
        "payment_promise", {"marca": resumen["marca"], "fecha": fecha.isoformat()}
    )
    return {
        "status": "success",
        "operation_id": operation_id,
        "resumen": (
            f"Promesa de pago de la tarjeta {resumen['marca']} terminada en "
            f"{resumen['ultimos_cuatro']} para el {fecha.isoformat()}"
        ),
        "saldo_pesos": resumen["saldo_pesos"],
        "saldo_dolares": resumen["saldo_dolares"],
        "advertencias": [
            "Los intereses se siguen devengando hasta el pago efectivo.",
            "Los saldos en pesos y en dolares se cancelan por separado.",
        ],
        "requiere_confirmacion": True,
    }


def confirm_payment_promise(operation_id: str, tool_context: ToolContext) -> dict:
    """Registra una promesa de pago ya preparada y confirmada por el usuario.

    Ejemplo de retorno:
        {"status": "success", "numero_de_caso": "CASO-1290", "marca": "visa",
         "fecha_comprometida": "2026-08-20",
         "mensaje": "Queda registrada la promesa de pago. No suspende los intereses."}
    """
    operacion, error = _tomar_operacion(operation_id, "payment_promise")
    if error:
        return error

    return {
        "status": "success",
        "numero_de_caso": f"CASO-{uuid.uuid4().int % 10000:04d}",
        "marca": operacion["marca"],
        "fecha_comprometida": operacion["fecha"],
        "mensaje": (
            "Queda registrada la promesa de pago. No suspende el devengamiento de "
            "intereses ni evita gestiones de cobranza previas a esa fecha."
        ),
    }


def escalate_to_human(motivo: str, tool_context: ToolContext) -> dict:
    """Deriva la conversacion a un representante humano.

    Usar ante fraude o desconocimiento de consumos, fallecimiento del titular,
    reclamos formales, deuda en gestion judicial, o cualquier pedido que las
    demas tools no cubran.

    Ejemplo de retorno:
        {"status": "success", "numero_de_caso": "CASO-3310",
         "mensaje": "Un representante va a continuar la conversacion."}
    """
    return {
        "status": "success",
        "numero_de_caso": f"CASO-{uuid.uuid4().int % 10000:04d}",
        "motivo_registrado": motivo,
        "mensaje": "Un representante va a continuar la conversacion por este mismo canal.",
    }


# --- Agente ---------------------------------------------------------------

root_agent = Agent(
    model="gemini-3.7-flash",
    name="asistente_banco",
    description=(
        "Asistente de atencion al cliente de un banco: consulta productos, "
        "paquetes de tarjetas, resumenes, prestamos y realiza gestiones."
    ),
    instruction=(
        "Sos el asistente de atencion al cliente de un banco. El usuario ya esta "
        "logueado: su identidad viaja sola hacia las tools, nunca se la pidas ni "
        "intentes pasarla como argumento.\n"
        "\n"
        "Politicas, no un orden fijo de pasos:\n"
        "- Toda afirmacion sobre la situacion del cliente sale de una tool. Si "
        "ninguna tool cubre lo que pide, decilo y ofrece derivar con "
        "`escalate_to_human`. Nunca inventes saldos, fechas, tasas ni requisitos.\n"
        "- Para cualquier tema de bonificaciones, upgrades o por que le cobran el "
        "paquete, usa `get_package_options`. Es la unica fuente valida de "
        "elegibilidad: no deduzcas ni estimes si califica.\n"
        "- No le pidas al cliente cuanto gana ni cuanto tiene invertido, y no se "
        "lo preguntes para 'calcular' nada. Si no califica para un paquete, "
        "explicale el requisito publicado que devuelve la tool y dejalo que el "
        "evalue.\n"
        "- Antes de cualquier gestion que modifique algo, llama primero a la tool "
        "`request_*`, mostrale al cliente el resumen, los efectos y el costo, y "
        "espera un si explicito. Recien entonces llama a la `confirm_*` con el "
        "operation_id. Un 'si' generico sin una operacion preparada no alcanza.\n"
        "- Si un upgrade no queda bonificado, decile el costo mensual antes de "
        "confirmar; puede avanzar igual si acepta pagarlo.\n"
        "- Cuando confirmes un cambio de paquete, informa la fecha de entrega que "
        "devuelve la tool y que llegan por correo. No calcules fechas vos.\n"
        "- Informa los montos tal como vienen. Los saldos en pesos y en dolares se "
        "informan por separado: no los sumes ni los conviertas. Las tasas de los "
        "prestamos se citan literalmente.\n"
        "- Si el cliente desconoce un consumo o menciona fraude, deriva con "
        "`escalate_to_human` en vez de intentar resolverlo.\n"
        "- No repitas datos sensibles innecesariamente y referite a las tarjetas "
        "por marca y ultimos cuatro digitos.\n"
        "\n"
        "Hablas en espaniol rioplatense, claro y breve, sin jerga bancaria "
        "innecesaria."
    ),
    tools=[
        get_customer_profile,
        get_products,
        get_package_options,
        get_card_statement,
        get_available_loans,
        request_package_upgrade,
        confirm_package_upgrade,
        request_investment_account,
        confirm_investment_account,
        request_payment_promise,
        confirm_payment_promise,
        escalate_to_human,
    ],
)
