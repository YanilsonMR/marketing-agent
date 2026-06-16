# TIER 3 — Outreach en Frio (Contratando Activamente / Alta Prioridad)

## Situacion
Esta empresa esta contratando activamente o tiene roles abiertos relacionados con los servicios que tu empresa ofrece. Estan en el mercado ahora mismo.

## Objetivo
Obtener una respuesta. Iniciar una conversacion. Hacer que sientan suficiente curiosidad para responder con "cuentame mas" o "claro, hablemos." Ese es el UNICO objetivo de este email. NO intentes vender, explicar todo o cerrar en este primer contacto.

## Estrategia
Aplica los principios de StoryBrand implicitamente — nunca nombres ni hagas referencia al framework:
- El destinatario es el heroe. Tu empresa es el guia.
- Comienza con un problema especifico que probablemente sienten ahora mismo. NO comiences con elogios o reconocimiento.
- Reduce la confusion — menos informacion es mas. Cada oracion extra reduce la probabilidad de respuesta.
- Haz que el siguiente paso sea pequenio y seguro.

El email debe leerse como: "Probablemente tienes este problema. Nosotros lo resolvemos. Hablamos?" Eso es todo el email en tres tiempos.

## Estructura del email (orden estricto)
1. **Saludo** — "Hola [Nombre]," (solo primer nombre, nunca "Estimado" ni "Querido")
2. **Problema** — 1-2 oraciones. Nombra un problema concreto que probablemente enfrentan segun su industria, tamanio de empresa y perfiles de contratacion. Se directo y especifico.
3. **Guia (tu empresa)** — 1-2 oraciones. Posiciona brevemente a la empresa como la solucion a ese problema especifico. Se concreto sobre lo que ofreces.
4. **CTA** — 1 oracion. Baja friccion, opcional, exploratorio. "Vale la pena una charla rapida?" o "Estas abierto a una conversacion corta?" NUNCA presiones con calendarios, demos o archivos adjuntos.
5. **Firma** — {sender_name} / {sender_title} / {company_name} (cada uno en su propia linea, separados por \n en JSON)

## Adaptacion de tono
Usa el cargo del contacto para calibrar el tono — pero NUNCA escribas titulos profesionales (Director, VP, CEO, Head of, etc.) en el email. Ni el del contacto ni ningun otro:
- **CEO/Fundador**: Enfocado en resultados, conciso. Habla en resultados: velocidad, costo, impacto en el roadmap.
- **CTO/VP Ingenieria**: Enfocado en ejecucion, creible. Habla en terminos practicos: calidad, preparacion para produccion, alineacion.
- **HR/Lider de Personas**: Enfocado en carga de trabajo, empatico. Habla de su dolor: fatiga de sourcing, calidad de candidatos, tiempo de contratacion.

## Guia de personalizacion
- **Perfiles de contratacion**: ESTA ES LA VARIABLE MAS IMPORTANTE. Referencia el tipo especifico de roles que estan contratando. Haz que el problema y la solucion sean concretos para ese tipo de rol.
- **Industria**: Usa el contexto de la industria para hacer el problema especifico.
- **Tamanio de empresa**: Empresas pequenias (<50) — enfatiza velocidad, proceso ligero, sin overhead. Empresas grandes (50+) — enfatiza volumen, ahorro de costos a escala.
- **ICP Rank**: Rank 1 = ultra preciso y muy especifico. Rank 2 = profesional y directo. Rank 3 = eficiente, corto, aun especifico.

## Longitud del email (critico)
- El cuerpo del email DEBE tener entre 80 y 150 palabras. Esto incluye saludo, cuerpo y firma.
- Si el email tiene menos de 80 palabras, sera rechazado automaticamente. Desarrolla mas el problema y la guia para alcanzar el minimo.
- Apunta a 90-120 palabras como rango ideal.

## Anti-patrones (critico)
- NO empieces el email con elogios, logros, noticias de financiamiento o reconocimiento de la empresa. EMPIEZA CON EL PROBLEMA.
- NO escribas mas de 4 parrafos cortos en total (saludo + problema + guia + CTA).
- NO listes multiples beneficios. Elige UN problema + UNA solucion. Eso es todo.
- NO uses lenguaje abstracto: "estrategico", "de clase mundial", "innovador", "de vanguardia", "transformador", "revolucionario."
- NO uses "nosotros" mas de dos veces en todo el email.
- NO especules: "Me imagino...", "Creo que podrias...". Plantea el problema directamente.
- NO uses preguntas como primera linea del cuerpo del email. Plantea el problema, no preguntes sobre el.
- NO escribas titulos profesionales en el cuerpo del email (Director, VP, CEO, CTO, Head of, Founder, HR, etc.). Estos causan fallo de validacion automatica.

## Formato de salida
Devuelve SOLO un objeto JSON valido. Sin texto antes ni despues. Sin bloques de markdown. Sin explicacion.

{
  "email_subject": "maximo 8 palabras, orientado al problema o curiosidad, especifico a su necesidad o industria, sin clickbait, sin asuntos genericos",
  "email_body": "formato de texto plano con \\n\\n entre parrafos, \\n entre lineas de firma, sigue la estructura del email de arriba, incluye firma al final. DEBE tener entre 80 y 150 palabras en total."
}
