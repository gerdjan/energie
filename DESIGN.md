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
