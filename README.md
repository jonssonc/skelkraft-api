# Skellefteå Kraft för Home Assistant

Hämtar data från Mina sidor hos Skellefteå Kraft via det inofficiella API:et
som biblioteket [`SkeKraft`](https://pypi.org/project/SkeKraft/) använder.

## Sensorer
- **Förbrukning denna månad** (per anläggning och leveranskategori, kWh)
- **Elområde, årsförbrukning, levereras från** (per anläggning)
- **Avtal** – slutdatum som tillstånd, produkt/pris/artiklar som attribut
- **Dygnsvärden rådata** (diagnostik) – visar vad API:et ger för dygnsvärden

## Inloggning
API:et stödjer **inte BankID direkt**. Skapa en gång ett användarnamn och lösenord:
1. Logga in på https://minasidor.skekraft.se/login med Mobilt BankID.
2. Gå till **Mitt konto → Inloggning** och skapa användarnamn och lösenord.

Integrationen loggar in med dessa, sparar token och förnyar den var 20:e minut.
Om förnyelsen misslyckas loggar den in på nytt automatiskt. Om lösenordet slutar
fungera ber Home Assistant dig logga in igen.

## Installation via HACS
1. HACS → ⋮ (uppe till höger) → **Anpassade databaser** (Custom repositories).
2. Lägg in adressen till detta GitHub-repo, typ **Integration**.
3. Sök efter "Skellefteå Kraft" i HACS, **Ladda ner**, starta om Home Assistant.
4. **Inställningar → Enheter och tjänster → Lägg till integration → Skellefteå Kraft.**

## Felsökning
Slå på debug-loggning i `configuration.yaml`:
```yaml
logger:
  logs:
    custom_components.skekraft: debug
```
Titta sedan i **Inställningar → System → Loggar**.
