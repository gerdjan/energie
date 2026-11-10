# Designdocument: energiekosten HW naar Frank

Dit document is bedoeld voor mensen en AI-tools die in deze repo gaan werken, zodat geen eerdere chatgeschiedenis nodig is. Lees dit eerst, daarna `PROMPT.md` voor de concrete opdracht voor functie 2.

## 1. Probleem
De eigenaar heeft een dynamisch energiecontract bij Frank Energie, zonnepanelen en een P1-meter-app ("HW", merk onbevestigd, mogelijk HomeWizard). Beide tonen dagelijks de kosten in euro's, maar de HW-bedragen zijn altijd hoger dan wat Frank toont, en alleen Frank klopt met de maandafrekening. De eigenaar wil (1) live uit HW-cijfers kunnen afleiden wat Frank gaat tonen en (2) kunnen voorspellen wat vandaag en morgen gaan kosten.

## 2. Functies
- **Functie 1 (klaar, in productie):** `index.html`. Invoer: afname kWh, teruglevering kWh, HW-bedrag. Uitvoer: verwacht Frank-bedrag. Coëfficiënten staan in de pagina, zijn aanpasbaar en worden lokaal in de browser bewaard (`localStorage`). Er worden geen verbruiksgegevens opgeslagen.
- **Functie 2 (nog te bouwen):** voorspelling van afname, teruglevering en kosten voor vandaag en morgen, op basis van weer, Frank-uurprijzen en een model. Zie `PROMPT.md`.

## 3. De formule van functie 1 en hoe die is gevonden
`Frank = HW − 0,165 × afname_kWh − 0,021 × teruglevering_kWh`

Afleiding:
- Eerste idee (op 3 dagen): `F ≈ 0,667 × HW + 0,10`. Dat bleek toeval en klopte niet op andere dagen.
- Aanname dat teruglevering de hoofdoorzaak van het verschil was: onjuist. Teruglevering speelt een kleine rol.
- Met 15 dagen aan data (afname, teruglevering, HW, Frank) gaf een kleinste-kwadratenfit `F = 1,000×HW − 0,165×afname − 0,021×teruglevering + 0,012` (RMSE ca. 0,02 euro, grootste fout 0,07). De constante en de HW-coëfficiënt zijn dus ongeveer 0 en 1.
- Daarna getest op dagen die niet in de fit zaten: 3, 5 en 4 dagen in drie rondes. Fouten meestal 0 tot 2 cent, soms 4 tot 10 cent.
- De simpele variant zonder teruglevering (`HW − 0,165 × afname`) is op dagen met veel teruglevering (10 tot 12 kWh) ongeveer 20 cent te hoog. Met de teruglevering-term klopt het binnen 1 tot 4 cent.
- Totaal nu: 27 dagen met echt Frank-bedrag, zie data in `PROMPT.md`.

Interpretatie (niet bewezen): HW telt gemiddeld ongeveer 16,5 cent per afgenomen kWh meer dan Frank. Het mechanisme is onbekend. Mogelijk heeft de HW-app een prijscomponent anders ingesteld dan het contract (belasting, opslag of btw).

Beperkingen:
- Het is een gemiddelde. Als tarieven wijzigen (nieuw belastingjaar, nieuwe opslag van Frank) verandert de 0,165 mee. Hercontroleer dan op een paar dagen.
- De formule beschrijft het dagbedrag van Frank zonder vastrecht en zonder belastingvermindering. Die staan op de maandfactuur.
- Het totale bereik van de test: afname tot 38 kWh per dag (laatste dagen buiten het gekalibreerde bereik van maximaal ca. 33 kWh).

## 4. Architectuurbesluiten
- **Statische site op GitHub Pages.** Geen backend en geen build-stap, zodat het simpel en gratis blijft.
- **Publieke repo.** Gratis GitHub Pages vereist dat. Daarom geen persoonlijke verbruiksgegevens in de repo, behalve de 27 kalibratiedagen in `PROMPT.md`. Geen tokens of sleutels committen.
- **Geen opslag van historische data in de app.** De gebruiker vult de cijfers in en ziet het resultaat. Dit was een bewuste vereenvoudiging van de scope.
- **Externe data (weer, Frank-prijzen):** pagina's gehost op een andere origin mogen in sommige omgevingen niet vrij fetchen. Test CORS. Als directe aanroep niet werkt, gebruik een geplande GitHub Action die JSON in `data/` schrijft.
- **Auto laden** wordt in deze fase bewust genegeerd in de interface. Wel robuust omgaan met uitschieters in de kalibratie.


## 4b. Besluit: gegevens ophalen via GitHub Actions
Sessies van AI-tools hebben vaak geen internet (DNS-fouten bij Open-Meteo en Frank zijn al voorgekomen), en browsers kunnen door CORS beperkt zijn. Daarom haalt een geplande GitHub Action (`.github/workflows/fetch-data.yml`, script `scripts/fetch_data.py`) dagelijks het weer en de Frank-uurprijzen op en commit ze als JSON in `data/`. De pagina leest alleen die JSON. De Action schrijft ook `data/status.json` (wat gelukt of mislukt is, per bron, met foutmelding en korte voorbeeldrespons), zodat een tool zonder internet of Actions-leesrechten kan zien wat er gebeurde door de repo te pullen.

## 5. Bronnen en aannames voor functie 2 (nog niet getest in deze repo)
- Weer: Open-Meteo (geen sleutel nodig), eventueel met KNMI HARMONIE als model. Locatie Meppel, ca. 52,70 N, 6,19 E.
- Frank-prijzen: openbare GraphQL-API zonder login. Endpoints en velden zoals genoemd in `PROMPT.md` komen uit community-voorbeelden en kunnen verouderd zijn. Controleer ze. De prijzen voor morgen staan er meestal rond 15:00 (Nederlandse tijd). De API levert mogelijk kwartierprijzen.
- Het Frank-prijsverloop ten opzichte van het bedrag dat de eigenaar daadwerkelijk betaalt per kWh moet uit de data gekalibreerd worden. Dit is de grootste onzekerheid in het model.

## 6. Bekende beperkingen en open punten
- Alleen daggegevens beschikbaar, geen uurdata. Een export van afname en teruglevering per uur uit HW of Home Assistant zou het model sterk verbeteren.
- 27 datapunten is weinig voor een model met weer-afhankelijkheid.
- De dagen 6 tot en met 10 november hebben geen Frank-bedrag (Frank werkte de afgelopen dagen niet bij); alleen HW-cijfers.
- Merk van de P1-meter is onbevestigd.

## 7. Conventies
- Nederlandse interface, komma als decimaalteken, euro's via `Intl.NumberFormat("nl-NL")`.
- Licht en donker thema via CSS-variabelen en `prefers-color-scheme`.
- Mobiel eerst (de pagina wordt vooral op een telefoon gebruikt).
- Functie 1 mag niet stuk gaan. Test met een bekende dag: 5 november (afname 20,72, teruglevering 2,34, HW 9,92) moet ongeveer 6,46 opleveren.

## 8. Werkwijze voor tools
- Werk `DESIGN.md` bij met wat je doet en besluit, zodat de volgende tool verder kan.
- Test API-aanroepen echt voordat je zegt dat ze werken, en meld het eerlijk als iets niet bereikbaar is.
- Commit in kleine stappen met duidelijke berichten.

## 9. Status: data-pipeline (gebouwd en in productie, 10 november 2026)

**Wat er is:**
- `scripts/fetch_data.py`: haalt Frank-uurprijzen en weer op (alleen Python-standaardbibliotheek). `scripts/test_parse.py`: offline tests met nagemaakte antwoorden (draaien ook in de Action).
- `.github/workflows/fetch-data.yml`: draait bij `workflow_dispatch`, bij een push op `scripts/**` of het workflowbestand, en dagelijks via cron op 05:00, 14:30 en 16:30 UTC (na ca. 15:00 Nederlandse tijd, zomer en winter). Commit het resultaat naar `main` met het ingebouwde `GITHUB_TOKEN`, ook na een mislukte fetch (zodat `status.json` altijd bijgewerkt wordt).
- Uitvoer in `data/`: `prijzen.json` (uurprijzen), `weer.json` (uurweer), `status.json` (per bron welke endpoints zijn geprobeerd, HTTP-status, aantal records, fouten) en `data/raw/` (korte voorbeeldantwoorden).

**Wat er werkt (geverifieerd in de eerste run, via `status.json`):**
- **Frank:** `POST https://graphql.frankenergie.nl/` met de dagquery `marketPrices(date: $date)` waarbij `$date` als `String!` wordt doorgegeven (variant `day_str`). Levert 24 uurrecords per dag met `from`, `till`, `marketPrice`, `marketPriceTax`, `sourcingMarkupPrice`, `energyTaxPrice`. Prijzen voor morgen waren bij de eerste run (21:33 NL-tijd) beschikbaar. Niet gelukt: de bereikvariant `marketPricesElectricity(startDate, endDate)` en de dagquery met `Date!` gaven "Graphql validation error". Het script probeert alles in die volgorde en onthoudt wat werkt. De tweede endpoint (`frank-graphql-prod.graphcdn.app`) en de terugvalbronnen (Energy-Charts, EnergyZero) zijn in de eerste run niet nodig geweest en dus **niet getest**.
- **Weer:** Open-Meteo forecast-endpoint met `models=knmi_seamless` (KNMI HARMONIE) en `past_days=60`, `forecast_days=4`. Alle 1536 uren (11 september tot en met 13 november) hadden geldige waarden. Per uur: temperatuur, globale straling, bewolking, wind (tijdzone Europe/Amsterdam). Let op: voor de historie is dit modeldata, geen meetstation.

**Bevindingen over de prijzen (all_in = marketPrice + marketPriceTax + sourcingMarkupPrice + energyTaxPrice, in EUR/kWh, aanname dat de componenten zo bij elkaar horen):**
- Opslag (`sourcingMarkupPrice`) is ca. 0,0182 per kWh en energiebelasting (`energyTaxPrice`) ca. 0,1109 per kWh, constant over de periode. De overige variatie zit in de marktprijs.
- Gemiddelde all-in prijs per dag varieerde sterk: ca. 0,17 tot 0,19 op 10 en 24 oktober (de twee dagen met 29,5 en 33 kWh afname en lage Frank-kosten) en ca. 0,44 tot 0,54 in november. Dat past bij de eerdere vermoedens dat die oktoberdagen goedkoop waren, maar is nog niet statistisch getoetst.
- **Nog niet onderzocht:** het verband tussen deze prijs en het verschil tussen HW en Frank (ca. 0,165 per kWh afname). Dat is de eerste vraag voor de kalibratie.

**Bekende beperkingen en aandachtspunten:**
- Geplande workflows in een publieke repo worden na ca. 60 dagen zonder repository-activiteit door GitHub uitgeschakeld. Of de dagelijkse data-commits van de Action dat voorkomen is niet geverifieerd. Controleer af en toe het tabblad Actions; bij uitschakeling is één klik op "Enable workflow" voldoende, of start hem handmatig via "Run workflow".
- Of een Action-commit een nieuwe GitHub Pages-deployment triggert is nog niet gecontroleerd. Controleer dat zodra de pagina `verwachting.html` bestaat.
- De Frank-API is niet officieel gedocumenteerd en kan zonder aankondiging veranderen. Een mislukte run schrijft de fout in `data/status.json` en laat de oude data staan.
- De terugvalbronnen rekenen met geschatte opslag en belasting (`APPROX` in `fetch_data.py`, niet geverifieerd). Hun uitvoer is gemarkeerd met `approx: true`.

**Handmatig starten:** GitHub, tabblad Actions, workflow "Data ophalen (weer en Frank-prijzen)", knop "Run workflow".

**Nog te doen:** kalibratie en model (sectie 3 en 4 van `PROMPT.md`), de pagina `verwachting.html` en de koppeling met `index.html`.
