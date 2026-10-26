<p align="center">
  <img src="custom_components/telia_prepaid/brand/icon.png" width="96" alt="">
</p>

# Telia Prepaid – Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/quenthal/telia_prepaid/actions/workflows/validate.yml/badge.svg)](https://github.com/quenthal/telia_prepaid/actions/workflows/validate.yml)

Tuo Telia Prepaid -liittymiesi saldot ja voimassaolon Home Assistantiin.
Tiedot luetaan samasta Minun Prepaid -palvelusta (prepaid.telia.fi), jota käytät
selaimella, joten kaikki tilillesi lisätyt liittymät tulevat mukaan.

*English: Home Assistant integration for Telia Finland prepaid subscriptions – balance,
bonus balance and expiry date. Uses your Minun Prepaid (Telia Tili) username and password.*

> [!IMPORTANT]
> **Epävirallinen projekti.** Tämä on yksityinen harrasteprojekti, jolla ei ole mitään
> yhteyttä Telia Companyyn tai Telia Finland Oyj:hin. Telia ei ole tehnyt, tarkastanut,
> hyväksynyt eikä tue tätä integraatiota. Integraatio käyttää Minun Prepaid -verkkopalvelun
> julkaisemattomia rajapintoja, jotka voivat muuttua tai lakata toimimasta milloin tahansa.
> Käyttö omalla vastuulla; ohjelmisto toimitetaan sellaisenaan ilman takuuta (ks. [LICENSE](LICENSE)).
> Älä ota yhteyttä Telian asiakaspalveluun tätä integraatiota koskevissa asioissa, vaan
> tee [issue](https://github.com/quenthal/telia_prepaid/issues).
>
> **Unofficial project.** This is an independent hobby project and is not affiliated with,
> endorsed by, sponsored by or supported by Telia Company or Telia Finland Oyj. It relies on
> undocumented interfaces of the Minun Prepaid web service that may change or stop working
> at any time. Use at your own risk; provided as is, without warranty (see [LICENSE](LICENSE)).
> Telia and the Telia logo are trademarks of Telia Company AB, used here only to identify
> the service the integration connects to.

## Sensorit

Jokaisesta liittymästä tulee oma laite (nimi sivulta, esim. "Veikon liittymä"):

| Sensori | Esimerkki | |
|---|---|---|
| Prepaid-saldo | 11,41 € | |
| Bonussaldo | 4,93 € | |
| Saldo yhteensä | 16,34 € | prepaid + bonus |
| Liittymä voimassa | 17.10.2027 klo 00.00 | aikaleima (tarkka hetki Telian `expiryDateUtc`-kentästä) |
| Voimassaoloa jäljellä | 364 d | kalenteripäivää Suomen aikaa |
| Liittymätyyppi | Telia Prepaid | diagnostiikka |
| SIM-kortin tyyppi | SIM-kortti | diagnostiikka |
| Liittymän tila | ACTIVE | diagnostiikka |

Tiedot päivittyvät oletuksena 6 tunnin välein (asetettavissa 30 min – 24 h).
*Voimassaoloa jäljellä* vaihtuu keskiyöllä Suomen aikaa, ja tilille myöhemmin lisätyt
liittymät tulevat mukaan seuraavassa päivityksessä.
Vahvistamattomat liittymät (odottavat PREPAID TILI OK -tekstiviestiä) ohitetaan.

## Asennus

**HACS:** HACS → oikean yläkulman valikko → *Mukautetut repositoriot* →
lisää `https://github.com/quenthal/telia_prepaid`, tyyppi *Integraatio* → asenna **Telia Prepaid**
→ käynnistä Home Assistant uudelleen.

**Käsin:** kopioi `custom_components/telia_prepaid` kansioon `/config/custom_components/`
ja käynnistä uudelleen.

Lisää sitten **Asetukset → Laitteet ja palvelut → Lisää integraatio → Telia Prepaid** ja
anna Minun Prepaid -tunnuksesi (sähköposti) ja salasanasi.

> Kirjautuminen vaatii salasanan. Jos olet kirjautunut Minun Prepaidiin vain
> sähköpostiin tulevalla koodilla, aseta salasana ensin Telia Tilissä.

## Miten se toimii

Kirjautuminen tehdään kuten selaimessa:

1. tunnus ja salasana → `id.telia.fi` (Telia Tili)
2. OIDC-ohjaus takaisin → `prepaid.telia.fi/auth/callback`
3. paluusivun palvelintoiminto vaihtaa kertakäyttökoodin pääsytunnisteeksi
4. liittymät luetaan sivun omilla palvelintoiminnoilla

Next.js-palvelintoimintojen tunnisteet vaihtuvat aina, kun Telia julkaisee sivustostaan
uuden version. Integraatio poimii ne sivun JavaScript-tiedostoista ja hakee ne uudelleen
automaattisesti, jos ne vanhenevat. Pääsytunnistetta ei tallenneta: jokainen päivitys
kirjautuu uudelleen.

## Vianetsintä

Jos Telia muuttaa sivustoaan niin, ettei tietoja enää tunnisteta, haetut vastaukset
tallennetaan kansioon `/config/telia_prepaid_debug/`. Salasanat, kertakäyttökoodit,
pääsytunnisteet, puhelinnumerot, nimet ja sähköpostiosoitteet on peitetty; saldot ja
päivämäärät näkyvät. Katso tiedostot silti läpi ennen kuin liität niitä julkiseen issueen.

Salasanaa kysytään uudelleen vain, jos Telia Tili hylkää tunnukset kahdesti peräkkäin.
Telian hetkelliset häiriöt näkyvät sensoreissa tilana *ei saatavilla*, ja haku yritetään
uudelleen 30 minuutin kuluttua.

Saman voi kokeilla ilman Home Assistantia: lataa julkaisun liitteenä oleva
`telia_prepaid_test.py` (pelkkä Python 3.10+, ei lisäkirjastoja) ja aja

```bash
python telia_prepaid_test.py oma@sahkoposti.fi -v --dump
```

Lisälokit Home Assistantiin:

```yaml
logger:
  logs:
    custom_components.telia_prepaid: debug
```

## Esimerkkiautomaatio

```yaml
automation:
  - alias: Prepaid-saldo vähissä
    triggers:
      - trigger: numeric_state
        entity_id: sensor.veikon_liittyma_saldo_yhteensa
        below: 3
    actions:
      - action: notify.notify
        data:
          message: "Prepaid-saldo on {{ states('sensor.veikon_liittyma_saldo_yhteensa') }} €"

  - alias: Prepaid-liittymä vanhenemassa
    triggers:
      - trigger: numeric_state
        entity_id: sensor.veikon_liittyma_voimassaoloa_jaljella
        below: 30
    actions:
      - action: notify.notify
        data:
          message: >-
            Prepaid-liittymä vanhenee
            {{ as_timestamp(states('sensor.veikon_liittyma_liittyma_voimassa')) | timestamp_custom('%d.%m.%Y klo %H.%M') }}
            – lataa saldoa.
```

## Kehitys

```bash
pip install pytest-homeassistant-custom-component
pytest tests                           # käynnistää Telia-jäljitelmän (tests/mock_server.py) itse
python tools/build_console.py          # -> dist/telia_prepaid_test.py
python tools/make_brand.py             # brändikuvat tools/telia_pebble.png:stä (vaatii pillow)
```

Uusi versio julkaistaan nostamalla `version` tiedostossa `manifest.json` ja lisäämällä
muutokset `CHANGELOG.md`:hen – GitHub Actions luo tagin ja julkaisun automaattisesti.

Tämä ei ole Telian virallinen integraatio, eikä Telia ole osallisena projektissa.
Telia-nimi ja -logo ovat Telia Company AB:n tavaramerkkejä; niitä käytetään vain kertomaan,
mihin palveluun integraatio liittyy. Tavaramerkkien käyttö ei tarkoita yhteistyötä eikä
Telian hyväksyntää.
