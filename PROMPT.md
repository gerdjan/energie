# Opdracht: voorspelling van energiekosten toevoegen aan bestaande statische web-app

> Lees eerst `DESIGN.md` voor achtergrond, besluiten en bevindingen. Dit bestand is de concrete opdracht voor functie 2.

## Doel en gebruiker
Ik ben een Nederlandse particulier met een dynamisch energiecontract bij Frank Energie, zonnepanelen en een P1-meter (door mij "HW" genoemd; het merk is niet bevestigd, mogelijk HomeWizard). Ik wil tijdens de dag weten wat mijn stroomkosten zijn en rond 15:00 wat de verwachting voor morgen is.

## Bestaande situatie (moet blijven werken!)
- Repo: https://github.com/gerdjan/energie, hosting via GitHub Pages (https://gerdjan.github.io/energie/). De repo is publiek.
- `index.html` is een zelfstandige statische pagina (geen build-stap) en is **functie 1**: ik vul afname (kWh), teruglevering (kWh) en het HW-bedrag (€) in, en de pagina rekent uit wat Frank toont:
  `Frank = HW − 0,165 × afname − 0,021 × teruglevering`
  Deze functie werkt goed en mag niet verdwijnen of veranderen. De formule is empirisch gevonden op 27 dagen (zie data hieronder), met afwijkingen van ongeveer 1 tot 4 cent per dag. Het bedrag is het dagbedrag van Frank zonder vastrecht en zonder belastingvermindering.
- Waarom het verschil bestaat: de HW-app rekent het verbruik met een prijs die gemiddeld ongeveer 16,5 cent per afgenomen kWh hoger ligt dan wat Frank rekent. Hoe dat precies komt is onbekend.

## Wat er gebouwd moet worden: functie 2 "Verwachting"
Een nieuw onderdeel (bijvoorbeeld een tweede pagina `verwachting.html` of een tab, met navigatie vanaf en naar `index.html`) dat voorspelt:
1. wat mijn afname, teruglevering en kosten **vandaag** worden (dag in zijn geheel, rekening houdend met wat ik al heb ingevuld, indien ik dat invul);
2. wat ze **morgen** worden.

Invoer voor de voorspelling:
- **Weer** (historisch voor kalibratie, verwachting voor vandaag en morgen): gebruik bij voorkeur Open-Meteo (gratis, geen sleutel). Haal per uur op: temperatuur, globale straling (shortwave radiation), bewolking en wind. Als het KNMI HARMONIE-model (via Open-Meteo, parameter `models`) beschikbaar is voor Nederland, gebruik die. Locatie: Meppel (Drenthe), ongeveer 52,70 N, 6,19 E. Controleer zelf de huidige API-documentatie.
- **Uurtarieven van Frank** voor vandaag en morgen. Frank heeft een openbare GraphQL-API zonder login. Voorbeelden uit het veld (kan veranderd zijn, controleer dit en test het echt):
  - POST naar `https://graphql.frankenergie.nl/` met een query als `marketPrices(date:"YYYY-MM-DD"){ electricityPrices{ from till marketPrice marketPriceTax sourcingMarkupPrice energyTaxPrice perUnit } }`
  - of POST naar `https://frank-graphql-prod.graphcdn.app` met `marketPricesElectricity(startDate:$startDate,endDate:$endDate){ from till marketPrice priceIncludingMarkup }`
  - Er zijn tegenwoordig mogelijk kwartierprijzen; reken om naar uurgemiddelden voor het model.
  - De prijzen van morgen verschijnen meestal rond 15:00 lokale tijd. Toon vóór die tijd duidelijk dat de prijzen van morgen er nog niet zijn.
- Mijn recente verbruik als context (optioneel, handmatig in te vullen): afname en teruglevering van vandaag tot nu.

## Technische randvoorwaarden
- Geen backend, geen database, geen opslag van persoonlijke gegevens, geen secrets in de repo. Mijn verbruiksgegevens mogen niet in de publieke repo komen, behalve de 27 kalibratiedagen hieronder.
- Eerst testen of de browser de API's direct kan aanroepen (CORS). Zo ja: haal live op in de pagina met `fetch`. Zo nee: maak een geplande **GitHub Action** (cron, ruim na 15:00 en een keer 's ochtends) die de gegevens ophaalt en als JSON in de repo zet (bijvoorbeeld `data/prijzen.json`, `data/weer.json`), die de pagina dan leest.
- Pagina's blijven statisch, werken op mobiel en desktop, met licht en donker thema, en zonder framework tenzij echt nodig. Nederlandse interface, getallen met komma als decimaalteken, euro's met `Intl.NumberFormat("nl-NL")`.
- Modelparameters in een los JSON-bestand, zodat ik ze later kan bijstellen zonder code te wijzigen.

## Modelopzet (begin simpel en toets het)
Ik heb alleen **daggegevens**, geen uurdata. Daarom:
1. **Afname per dag** ≈ functie van de gemiddelde buitentemperatuur (bijvoorbeeld graaddagen met een basislijn plus vaste basislast). Gebruik een robuuste fit, omdat sommige dagen uitschieters zijn doordat ik de auto heb opgeladen (zie hieronder).
2. **Teruglevering per dag** ≈ functie van de dagsom van de zonnestraling.
3. **Verdeling over de uren**: neem een plausibel huishoudprofiel aan (lage nachtbasis, ochtend- en avondpiek) voor afname, en leg de teruglevering volgens het zonprofiel van die dag. Maak dit profiel configureerbaar. Later kan ik uurdata aanleveren om het te verbeteren.
4. **Kosten per uur** = afname × (uurprijs voor mij) − teruglevering × (terugleverprijs), opgeteld tot dagkosten. Uitdaging: het precieze verband tussen Frank-uurprijs en mijn werkelijke kosten per kWh moet uit de data gekalibreerd worden. Gebruik de 27 dagen: bereken voor elke dag de voorspelde kosten met de werkelijke afname, teruglevering, het historische weer en de historische Frank-uurprijzen, en vergelijk met het werkelijke Frank-bedrag (kolom `frank_eur`). Pas de aannames aan tot dat goed past.
5. **Toon onzekerheid**: laat een bandbreedte zien (bijvoorbeeld ±1 standaardafwijking van de backtest-fout), niet alleen één getal.
6. **Backtest**: lever een script of sectie die de nauwkeurigheid op de 27 dagen laat zien (gemiddelde en maximale fout), met leave-one-out als dat kan. Wees eerlijk over de resultaten: met 27 dagen en zonder uurdata is dit een grove schatting.

## Auto laden (bewust niet in scope)
Ik laad soms mijn elektrische auto thuis. Voor deze versie negeren we dat in de interface. In de kalibratie moeten uitschieters wel robuust behandeld worden (dagen met zeer hoge afname ten opzichte van wat de temperatuur voorspelt), zodat ze het model niet verstoren. Ik kan later per dag aangeven welke dagen auto-laaddagen zijn.

## Opleveren
- Werkende code in de repo, bestaande `index.html` onaangetast (behalve eventueel een link naar de nieuwe pagina).
- Korte README-sectie: wat de bronnen zijn, hoe het model werkt, hoe parameters aangepast worden, hoe de Action werkt.
- Een korte rapportage van de backtest en een lijst met bekende beperkingen.
- Commit in kleine, duidelijke stappen. Test API-aanroepen echt voordat je ze als werkend presenteert, en meld het als iets niet bereikbaar of anders is dan hier beschreven.
- Werk `DESIGN.md` bij met wat je hebt gedaan, besloten en geleerd.

## Data: 27 dagen met echt Frank-bedrag (1 oktober tot en met 5 november 2026)
Kolommen: datum, afname kWh, teruglevering kWh, HW-bedrag €, Frank-bedrag € (dagbedrag, zonder vastrecht en belastingvermindering). Ontbrekende datums zijn dagen waarvan ik de cijfers niet heb.

```csv
datum,afname_kwh,teruglevering_kwh,hw_eur,frank_eur
2026-10-01,5.3,6.7,0.96,-0.04
2026-10-02,5.0,10.3,0.22,-0.80
2026-10-03,6.4,10.6,1.23,-0.01
2026-10-04,7.46,12.13,1.73,0.28
2026-10-05,9.5,7.5,2.80,1.09
2026-10-07,7.3,11.6,1.08,-0.35
2026-10-08,22.9,1.0,7.28,3.49
2026-10-09,25.9,0.0,7.21,2.94
2026-10-10,29.53,4.29,6.37,1.43
2026-10-11,25.13,1.13,6.94,2.79
2026-10-12,14.5,6.44,5.07,2.56
2026-10-13,11.1,0.6,4.25,2.40
2026-10-14,11.1,4.8,4.06,2.13
2026-10-15,6.4,8.3,1.52,0.30
2026-10-22,13.5,0.4,5.06,2.82
2026-10-23,18.3,1.8,6.21,3.17
2026-10-24,33.2,0.0,7.08,1.62
2026-10-27,11.45,2.18,4.46,2.54
2026-10-28,12.69,3.15,5.85,3.70
2026-10-29,9.91,3.37,4.79,3.09
2026-10-30,14.97,0.27,7.51,5.12
2026-10-31,9.37,3.4,3.69,2.08
2026-11-01,17.03,0.01,8.36,5.56
2026-11-02,15.83,2.77,6.89,4.21
2026-11-03,12.13,1.5,5.65,3.62
2026-11-04,14.91,0.96,6.95,4.48
2026-11-05,20.72,2.34,9.92,6.46
```

Dagen zonder Frank-bedrag (alleen HW, geen kalibratie op kosten mogelijk, wel bruikbaar voor een verbruiksmodel): 2026-11-06 (24,7 kWh afname, 1,4 kWh terug, HW 12,85), 11-07 (38,4 / 0 / 18,59), 11-08 (21,0 / 0,1 / 10,06), 11-09 (22,2 / 1,4 / 12,88), 11-10 (13,5 / 0 / 7,56).
Sommige afname- en terugleveringscijfers zijn door de bron afgerond op 0,1 kWh.
