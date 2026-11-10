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
- Een Action-commit triggert wel een nieuwe GitHub Pages-build (geverifieerd via de Pages-API: laatste build was gepusht door github-actions[bot], status built).
- De Frank-API is niet officieel gedocumenteerd en kan zonder aankondiging veranderen. Een mislukte run schrijft de fout in `data/status.json` en laat de oude data staan.
- De terugvalbronnen rekenen met geschatte opslag en belasting (`APPROX` in `fetch_data.py`, niet geverifieerd). Hun uitvoer is gemarkeerd met `approx: true`.

**Handmatig starten:** GitHub, tabblad Actions, workflow "Data ophalen (weer en Frank-prijzen)", knop "Run workflow".

## 10. Status: model, kalibratie en verwachtingspagina (gebouwd, 10 november 2026)

**Bestanden**
- `data/dagen.csv`: de kalibratiedagen (datum, afname, teruglevering, HW-bedrag, Frank-bedrag; Frank leeg als onbekend). Hier voeg je nieuwe dagen aan toe (een regel per dag). Bij een wijziging van dit bestand draait de Action en kalibreert hij het model opnieuw.
- `scripts/calibrate.py`: kalibreert (alleen standaardbibliotheek) en schrijft `data/model.json` en `data/backtest.json`. Draait in de Action direct na het ophalen.
- `verwachting.html`: leest `data/model.json`, `prijzen.json`, `weer.json` en `status.json`. Doet alle berekeningen in de browser. Heeft geen invoer nodig, maar je kunt je afname en HW-bedrag tot nu toe invullen voor een scherpere verwachting voor vandaag (invoer wordt per dag lokaal onthouden).
- `index.html` (functie 1) is ongewijzigd, op één link naar `verwachting.html` na. Getest in een browser: 5 november (20,72 kWh, 2,34 kWh, HW 9,92) geeft 6,45, werkelijk 6,46.

**Het model (per dag)**
1. `afname = 27.88 -1.362 × gemiddelde temperatuur` (kWh). De fit is robuust: dagen die ver boven de lijn liggen worden herhaaldelijk weggelaten. Uitbijters op dit moment: 2026-10-08, 2026-10-09, 2026-10-10, 2026-10-11, 2026-10-24, 2026-11-07, waarschijnlijk auto laden (niet bevestigd; de eigenaar heeft de laaddagen niet doorgegeven).
2. `teruglevering = max(0, 2.11 + 2.53 × zonnestraling − 0.178 × afname)`. Zonnestraling is de dagsom van de uurlijkse globale straling in kWh/m².
3. `kosten (Frank-dagbedrag) = 1.078 × afname × p_dag − 0.527 × teruglevering × p_zon − 0.144 × afname`. `p_dag` is de gemiddelde all-in uurprijs van de dag, `p_zon` de met zonnestraling gewogen all-in prijs. Dit is de sterkste en meest verrassende bevinding: een afgenomen kWh kost in het Frank-dagbedrag ongeveer 1,08 × de all-in prijs min 14 cent, en een teruggeleverde kWh brengt ongeveer 0,53 × de all-in prijs op. Het waarom is niet onderzocht (de salderingsregeling en hoe de energiebelasting in het dagbedrag zit spelen vermoedelijk mee). Het is een empirische fit.
4. Voor het deel van de dag dat al voorbij is gebruikt de pagina een aangenomen dagprofiel (`dagprofiel_afname` in `model.json`; **een aanname, niet uit data**) en de zonnestraling voor de teruglevering. Wat je zelf invult wordt omgerekend met de formule van functie 1.

**Hoe goed is het? (leave-one-out backtest op de dagen met een echt Frank-bedrag, `data/backtest.json`)**
- Kosten, hele keten (verbruik voorspeld uit weer, daarna kosten uit prijzen): zonder uitbijters gemiddelde fout 0.77 euro, RMSE 0.92 euro (n=22); op alle dagen inclusief mogelijke laaddagen RMSE 1.08 euro (n=27).
- Kosten als het verbruik wél bekend is (alleen het prijsmodel): RMSE 0.34 euro, grootste fout 1.14 euro. De fout in de keten komt dus vooral uit de voorspelling van het verbruik, niet uit de prijzen.
- De afwijking van de verbruiksvoorspelling zelf: afname gemiddeld 4.6 kWh (met laaddagen erbij), teruglevering gemiddeld 1.7 kWh.
- De bandbreedte in de pagina is ± de RMSE van de keten zonder uitbijters. Voor vandaag met invoer wordt die kleiner naarmate de dag vordert.
- Eerlijke conclusie: dit geeft een bruikbare orde van grootte (typisch ± 1 euro op een dagbedrag van 3 tot 10 euro), geen exacte voorspelling. Met uurdata van afname en teruglevering en met de laaddagen als vinkje zou het veel beter kunnen.

**Wat nog niet gedaan is, en keuzes**
- Dag 2026-11-10 is uitgesloten van de kalibratie: de cijfers waren van een onvolledige dag ("tot nu toe"). Dagen 6 tot en met 9 november staan wel in `dagen.csv` maar zonder Frank-bedrag; ze dragen alleen bij aan het verbruiksmodel. Vul het Frank-bedrag in zodra het bekend is.
- Auto laden wordt niet als invoer behandeld. Verwachtingen gaan uit van een dag zonder laden. Een volgende stap kan een vinkje per dag in `dagen.csv` zijn (kolom `auto`), zodat die dagen expliciet worden weggelaten in plaats van statistisch.
- Het weermodel gebruikt alleen gemiddelde temperatuur en dagsom van straling. Wind en bewolking gaven in de verkenning geen duidelijke verbetering. De historie is modeldata van Open-Meteo (KNMI HARMONIE), geen meetstation.
- Het aantal datapunten is klein (27 met Frank-bedrag), de coëfficiënten kunnen verschuiven bij nieuwe data. Elke nieuwe dag in `dagen.csv` helpt. In december en later zijn temperatuur en zon heel anders dan in de kalibratieperiode (oktober, begin november); extrapoleren kan fout gaan.
- De formule van functie 1 en het kostenmodel zijn niet hetzelfde: functie 1 rekent achteraf uit HW-cijfers (nauwkeurig tot enkele centen), het kostenmodel voorspelt vooruit.
