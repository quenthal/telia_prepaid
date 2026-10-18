# Muutokset

## 1.0.0

Ensimmäinen julkaisu.

- Kirjautuminen Telia Tilin (id.telia.fi) tunnuksella ja salasanalla
- Sensorit: prepaid-saldo, bonussaldo, saldo yhteensä, voimassaolo (aikaleima),
  päiviä jäljellä, liittymätyyppi, SIM-kortin tyyppi ja liittymän tila
- Kaikki tilin vahvistetut liittymät omina laitteinaan
- Palvelintoimintojen tunnisteet haetaan automaattisesti uudelleen, kun Telia päivittää sivustonsa
- Omat brändikuvat (Home Assistant 2026.3+)
- Liitteenä konsolitesti `telia_prepaid_test.py` (Python 3.10+, ei lisäkirjastoja)
