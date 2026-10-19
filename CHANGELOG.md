# Muutokset

## 1.0.1

- Korjattu: kirjautuminen epäonnistui Home Assistantissa virheellä "Kirjautumis- tai
  tilisivua ei tunnistettu". aiohttp lähetti Telia Tilin istuntoevästeen
  lainausmerkeissä, jolloin id.telia.fi ohjasi takaisin kirjautumissivulle.
  Konsolitesti ei kärsinyt viasta, koska se käyttää Pythonin omaa evästekäsittelyä.
- Selkeämpi virheilmoitus, jos Telia Tili ei tunnista istuntoa.
- Testipalvelin tarkistaa nyt raa'an Cookie-otsakkeen kuten oikea palvelu.

## 1.0.0

Ensimmäinen julkaisu.

- Kirjautuminen Telia Tilin (id.telia.fi) tunnuksella ja salasanalla
- Sensorit: prepaid-saldo, bonussaldo, saldo yhteensä, voimassaolo (aikaleima),
  päiviä jäljellä, liittymätyyppi, SIM-kortin tyyppi ja liittymän tila
- Kaikki tilin vahvistetut liittymät omina laitteinaan
- Palvelintoimintojen tunnisteet haetaan automaattisesti uudelleen, kun Telia päivittää sivustonsa
- Omat brändikuvat (Home Assistant 2026.3+)
- Liitteenä konsolitesti `telia_prepaid_test.py` (Python 3.10+, ei lisäkirjastoja)
