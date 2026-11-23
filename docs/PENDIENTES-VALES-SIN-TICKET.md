# Vales generados sin ticket de OxxoGas (pendientes de cerrar)

> Documentado el **2026-11-22**. No es un error del sistema: son vales que se
> generaron en Go Vale y **nunca se les capturó el ticket**, así que quedaron
> abiertos. Se listan aquí para cerrarlos a mano más adelante.

## Por qué no aparecen en el módulo de Tickets

El módulo **Tickets de OxxoGas** de Admon muestra como «Ticket pendiente» a los
vales que cumplen **las tres** condiciones:

1. `Estatus = 'GENERADO'` (o sea, el vale **ya existe** en Go Vale: no aparece
   antes, para no prometer un vale que todavía no se emitió),
2. `IdTicketCierre IS NULL` (todavía no se capturó el ticket), y
3. `FechaSolicitud >= ayer`.

La tercera condición es deliberada: la pantalla es para **esperar la foto del
ticket recién generado**, no un buzón de deuda vieja. Por eso los de esta lista,
que ya pasaron de un día, no salen.

## Los 5 pendientes (al 2026-11-22)

| Vale | Solicitado | Placa | Monto | Solicitante | Folio Go Vale |
|---|---|---|---|---|---|
| **#57** | 2026-11-19 | RYL615A | $500.00 | José Salazar | 697155817 |
| **#56** | 2026-11-19 | SJA350C | $500.00 | Alfredo Rendón | 151015344 |
| **#53** | 2026-11-17 | RWS675B | $500.00 | Daniel Quintanilla | 083684492 |
| **#37** | 2026-10-28 | RYL615A | $500.00 | José Salazar | 854361404 |
| **#31** | 2026-10-14 | TDX-777-B | $500.00 | Héctor Peña | 542300688 |

Total: **$2,500** en 5 vales.

## Cómo consultarlos cuando haga falta

```sql
SELECT S.Id, S.FechaSolicitud, S.MontoUnit, S.Placa, S.IdValeGoVale,
       U.Nombre AS Solicitante
FROM HUB_SolicitudVales S
LEFT JOIN HUB_Users U ON U.Id = S.IdSolicitante
WHERE S.Estatus = 'GENERADO' AND S.IdTicketCierre IS NULL
ORDER BY S.FechaSolicitud DESC;
```

## Dos formas de cerrarlos

- **Capturar el ticket**: si el ticket existe en papel/foto, se registra y el
  vale pasa solo a `CERRADO` con `IdTicketCierre` (desde Field o con el botón
  **Capturar** del módulo en Admon).
- **Cancelar el vale**: si el combustible no se cargó, el vale queda como
  `CANCELADO`. **Ojo:** cancelar en la app no devuelve el saldo en Go Vale; si
  el vale se va a anular de verdad, hay que hacerlo también en Go Vale, y eso
  lo decide quien administra la cuenta.
