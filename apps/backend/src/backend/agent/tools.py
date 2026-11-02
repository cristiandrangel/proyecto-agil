import hashlib
import json
from uuid import UUID

from agil_shared.errors import DomainError


def _schema(name, description, properties):
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


TEXT = {"type": "string"}
OPTIONAL = {"type": ["string", "null"]}
TOOL_SCHEMAS = [
    _schema(
        "locate_customer",
        "Localiza por teléfono O identificación. Interpreta el tipo expresado en lenguaje "
        "natural y consulta usando su código canónico, no su nombre coloquial. "
        "En esta demo, cédula de ciudadanía o cédula se consulta como CC. "
        "Separa tipo y número aunque el usuario los escriba en otro orden. "
        "Solo devuelve una pista de identidad, nunca cartera ni autenticación.",
        {
            "phone_e164": OPTIONAL,
            "document_type": {
                **OPTIONAL,
                "description": "Código canónico del tipo de documento. CC = cédula de "
                "ciudadanía; interpretar 'cédula' como CC en esta demo. No enviar 'cédula', "
                "'cedula' ni el nombre desarrollado como valor del código. Si indica "
                "otro tipo, no convertirlo a CC por suposición.",
            },
            "document_number": {
                **OPTIONAL,
                "description": "Identificación en el formato canónico de central, sin el nombre "
                "del tipo. En números, elimina puntos o espacios que sean separadores de "
                "agrupación, conservando todos los dígitos y ceros iniciales. Conserva letras "
                "o caracteres significativos de otros documentos; aclara formatos ambiguos. "
                "No tratarlo como dinero ni usarlo como PIN.",
            },
        },
    ),
    _schema(
        "manage_identity",
        "Confirma o rechaza el candidato según la intención del cliente. change_customer "
        "cierra la sesión revocando el acceso y permite gestionar otro titular con nuevo PIN. "
        "Confirmar activa el brazo estático del PIN con tres oportunidades; nunca autentica "
        "ni autoriza la cartera. No recibe códigos.",
        {"action": {"type": "string", "enum": [
            "confirm_candidate", "reject_candidate", "change_customer",
        ]}},
    ),
    _schema(
        "list_debts", "Consulta deudas y acuerdos vigentes del registro autenticado, sin seleccionar ni crear órdenes.", {"service_type": OPTIONAL}
    ),
    _schema(
        "select_debt", "Selecciona una deuda autorizada y recupera su acuerdo vigente y enlace reutilizable, si existen.", {"debt_id": TEXT}
    ),
    _schema(
        "create_full_payment", "Crea enlace por saldo vigente sin descuento.", {"debt_id": TEXT}
    ),
    _schema(
        "quote_agreement",
        "Propone pagar al menos el 80%, sin liquidar ni aceptar todavía.",
        {"debt_id": TEXT, "offer_amount_usd": TEXT},
    ),
    _schema(
        "accept_agreement",
        "Acepta una propuesta previa solo en un mensaje posterior y obtiene enlace.",
        {"agreement_id": TEXT},
    ),
    _schema(
        "verify_payment",
        "Verifica pago real y titularidad; obligatorio al recibir un comprobante.",
        {"debt_id": TEXT, "payment_reference": OPTIONAL},
    ),
    _schema(
        "handoff_human",
        "Solicita atención humana y suspende automatización.",
        {
            "reason": {
                "type": "string",
                "enum": [
                    "requested",
                    "dispute",
                    "below_minimum",
                    "payment_unverified",
                    "technical_failure",
                ],
            },
            "offer_amount_usd": OPTIONAL,
            "summary": TEXT,
        },
    ),
]


class ToolRuntime:
    def __init__(self, event, identity, central, handoff, observability):
        self.event, self.identity, self.central = event, identity, central
        self.handoff, self.observability = handoff, observability
        self.pending_agreement_id = None
        self.active_order_id = None
        self.phase = "identify"

    def catalog(self):
        if self.handoff.blocked(self.event.thread_id):
            return []
        verified = self.identity.snapshot(self.event.thread_id)["verified"]
        return [
            s for s in TOOL_SCHEMAS
            if verified or s["name"] in {"locate_customer", "manage_identity", "handoff_human"}
        ]

    def key(self, name, args):
        raw = json.dumps({"event": str(self.event.id), "tool": name, "args": args}, sort_keys=True)
        return "tool-" + hashlib.sha256(raw.encode()).hexdigest()

    async def execute(self, name, args):
        schema = next((s for s in self.catalog() if s["name"] == name), None)
        if schema is None:
            raise DomainError("tool_forbidden", "Herramienta no autorizada.", 403)
        if not isinstance(args, dict) or set(args) != set(schema["parameters"]["properties"]):
            raise DomainError("invalid_tool_arguments", "Argumentos de herramienta inválidos.", 422)
        for key, value in args.items():
            spec = schema["parameters"]["properties"][key]
            if value is None and isinstance(spec["type"], list):
                continue
            if (
                not isinstance(value, str)
                or len(value) > 1000
                or ("enum" in spec and value not in spec["enum"])
            ):
                raise DomainError(
                    "invalid_tool_arguments", "Argumentos de herramienta inválidos.", 422
                )
        args = {k: v for k, v in args.items() if v is not None}
        with self.observability.span(
            "tool", event_id=self.event.id, thread_id=self.event.thread_id, tool=name,
            input={"arguments": args, "phase_before": self.phase,
                   "identity": self.identity.snapshot(self.event.thread_id)},
        ) as trace:
            result = await self._execute(name, args)
            if trace is not None:
                summary = {"phase": self.phase}
                if isinstance(result, dict):
                    summary["result_status"] = result.get("status")
                    summary["candidate_count"] = result.get("candidate_count")
                    if name == "list_debts" and isinstance(result.get("items"), list):
                        summary["debt_count"] = len(result["items"])
                trace.update(output={"result": result, "phase_after": self.phase}, **summary)
            return result

    async def _execute(self, name, args):
        if name == "locate_customer":
            self.pending_agreement_id = self.active_order_id = None
            self.phase = "identify"
            return await self.identity.locate(self.event.thread_id, args, self.event.message_id)
        if name == "manage_identity":
            result = await self.identity.manage(self.event.thread_id, args["action"])
            self.pending_agreement_id = self.active_order_id = None
            self.phase = "awaiting_pin" if result.get("requires_pin") else "identify"
            return result
        if name == "handoff_human":
            self.phase = "handoff_requested"
            return await self.handoff.request(self.event, **args)
        snapshot = self.identity.snapshot(self.event.thread_id)
        grant = snapshot["grant_token"]
        if not snapshot["verified"] or not grant:
            raise DomainError("identity_required", "Valida el registro para continuar.", 403)
        if name == "list_debts":
            self.phase = "select_debt"
            return await self.central.request("GET", "/debts", grant=grant, params=args)
        if name == "select_debt":
            UUID(args["debt_id"])
            result = await self.identity.select_debt(self.event.thread_id, args["debt_id"])
            self.pending_agreement_id = self.active_order_id = None
            self.phase = "discuss_payment"
            agreement = result.get("active_agreement")
            if agreement:
                self.pending_agreement_id = agreement["agreement_id"]
                if agreement["status"] == "propuesto":
                    self.phase = "confirm_agreement"
                elif agreement["status"] == "aceptado" and agreement.get("order_id"):
                    self.active_order_id = agreement["order_id"]
                    self.phase = "await_payment"
                    result["payment_link"] = f"[[PAYMENT:{self.active_order_id}]]"
            return result
        debt_id = args.get("debt_id") or snapshot["selected_debt_id"]
        if not debt_id or str(snapshot["selected_debt_id"]) != str(debt_id):
            raise DomainError(
                "debt_selection_required", "Selecciona esa deuda antes de continuar.", 409
            )
        debt = await self.central.request("GET", f"/debts/{debt_id}", grant=grant)
        if name == "verify_payment":
            result = await self.central.request("GET", "/payments/verify", grant=grant, params=args)
            if result.get("status") == "applied":
                self.phase = "payment_verified"
            return result
        payload = {"expected_version": debt["version"]}
        if name == "create_full_payment":
            path = "/orders"
            payload["debt_id"] = str(debt_id)
        elif name == "quote_agreement":
            path = "/agreements/quote"
            payload.update(args, source_message_id=self.event.message_id)
        elif name == "accept_agreement":
            UUID(args["agreement_id"])
            if args["agreement_id"] != self.pending_agreement_id:
                raise DomainError(
                    "agreement_selection_required",
                    "Confirma la propuesta vigente de la deuda seleccionada.",
                    409,
                )
            path = f"/agreements/{args['agreement_id']}/accept"
            payload["source_message_id"] = self.event.message_id
        else:
            raise DomainError("tool_unknown", "Herramienta desconocida.", 422)
        result = await self.central.request(
            "POST", path, json=payload, grant=grant, idempotency_key=self.key(name, args)
        )
        if result.get("requires_human"):
            self.phase = "handoff_requested"
            return await self.handoff.request(
                self.event,
                reason="below_minimum",
                summary="Oferta por debajo del 80% de la deuda seleccionada.",
                offer_amount_usd=args.get("offer_amount_usd"),
            )
        if name == "quote_agreement":
            self.pending_agreement_id = str(result.get("agreement_id", result.get("id")))
            self.phase = "confirm_agreement"
        if result.get("order_id"):
            self.active_order_id = str(result["order_id"])
            self.phase = "await_payment"
            result["payment_link"] = f"[[PAYMENT:{self.active_order_id}]]"
        return {k: v for k, v in result.items() if k not in {"capability", "grant_token", "token"}}
