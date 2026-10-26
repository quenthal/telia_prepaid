# Muutokset

Versiot ovat muotoa `VVVV.KK.N`: julkaisuvuosi, -kuukausi ja kuukauden julkaisun
järjestysnumero (esim. 2026.10.1 = lokakuun 2026 ensimmäinen julkaisu).

## 2026.10.1

- Siirrytty kalenteriversiointiin. Sisältö on sama kuin versiossa 1.1.1.

## 1.1.1

- Kuvakkeena ja logona Telian logo (läpinäkyvä tausta, vaalea ja tumma teema).
- README: selvä maininta, että projekti on epävirallinen eikä liity Teliaan.

## 1.1.0

- Korjattu: integraatio saattoi pyytää salasanaa uudelleen, vaikka tunnukset olivat
  kunnossa. Kirjautumisen myöhempien vaiheiden virheet (koodin vaihto, OIDC-ohjaus,
  liittymähaku) tulkittiin väärin tunnusvirheiksi, jolloin Home Assistant lopetti
  päivitykset. Nyt salasanaa kysytään vain, jos Telia Tili hylkää tunnukset kahdesti
  peräkkäin; palomuurin sivu (403) ja kirjautumisrajoitus (429) ovat tilapäisiä virheitä.
- Korjattu varoitus "has an update listener and should use it for scheduling a reload",
  joka tuli salasanan uusimisen yhteydessä (lakkaisi toimimasta HA 2026.12:ssa).
  Asetusten muutos lataa integraation uudelleen HA:n omalla mekanismilla.
  Vaatii nyt Home Assistant 2025.8:n tai uudemman.
- Epäonnistunut haku yritetään uudelleen 30 minuutin kuluttua eikä vasta seuraavalla
  päivitysvälillä.
- Tilille myöhemmin lisätyt liittymät saavat sensorinsa ilman uudelleenkäynnistystä.
- *Voimassaoloa jäljellä* vaihtuu keskiyöllä Suomen aikaa.
- Vianetsintätiedostoista peitetään myös puhelinnumerot, nimet ja sähköpostiosoitteet.
- Testit käynnistävät Telia-jäljitelmän itse, ja ne kattavat Telian hetkelliset viat.

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
