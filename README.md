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
tallennetaan kansioon `/config/telia_prepaid_debug/`. Salasanat, kertakäyttökoodit ja
pääsytunnisteet on peitetty, mutta tiedostoissa näkyvät puhelinnumerosi ja saldosi.

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
python tests/mock_server.py &          # paikallinen Telia-jäljitelmä
pytest tests
python tools/build_console.py          # -> dist/telia_prepaid_test.py
python tools/make_brand.py             # brändikuvat (vaatii pillow)
```

Uusi versio julkaistaan nostamalla `version` tiedostossa `manifest.json` ja lisäämällä
muutokset `CHANGELOG.md`:hen – GitHub Actions luo tagin ja julkaisun automaattisesti.

Tämä ei ole Telian virallinen integraatio, eikä Telia ole osallisena projektissa.
Kuvake on projektin oma.
