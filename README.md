# Face D — Monitoraggio prezzi (prototipo)

App interna HCS S.r.l. per controllare i prezzi dei prodotti Face D sul web: rivenditori autorizzati, Amazon.it (API ufficiali SP-API) e, nelle fasi successive, siti sconosciuti.

## Come è fatta

| Parte | Dove | Cosa fa |
|---|---|---|
| `supabase/schema.sql`, `seed.sql` | Supabase (progetto `faced-price-monitor`, Francoforte) | Database: prodotti, siti, pagine monitorate, rilevazioni, venditori. Accesso solo con login. |
| `collector/` | GitHub Actions | Raccolta prezzi: aggiorna i prezzi di riferimento da faced.com, legge le pagine prodotto dei siti, legge le offerte Amazon.it. |
| `.github/workflows/collect.yml` | GitHub Actions | Esegue la raccolta **lunedì e giovedì** alle 06:17 (ora italiana, inverno). Si può avviare a mano da *Actions → Raccolta prezzi → Run workflow*. |
| `dashboard/index.html` | Browser | Matrice prodotto × sito, tagli oltre 20%, venditori Amazon, pagine monitorate, storico raccolte. |

## Regole

- **Prezzo di riferimento** = prezzo su faced.com. Se su faced.com c'è un prezzo barrato più alto, vale il prezzo barrato.
- **Scostamento** = (prezzo rilevato − riferimento) / riferimento. Soglia di allarme: −20%.
- **Possibile bundle**: segnalato in automatico se il titolo contiene parole come kit, cofanetto, 2x, "+"; va confermato a mano.
- **Venditori Amazon**: Amazon dà solo il codice venditore; il nome e lo stato (autorizzato / non autorizzato) si impostano dalla dashboard. Amazon stesso è già segnato come autorizzato.

## Segreti (GitHub → Settings → Secrets and variables → Actions)

| Nome | Dove si trova |
|---|---|
| `SUPABASE_URL` | `https://ddnsukwzonszpbeyrvwp.supabase.co` |
| `SUPABASE_SECRET_KEY` | Supabase → Project Settings → API Keys → *Secret key* |
| `SPAPI_CLIENT_ID` | Solution Provider Portal → app "FaceD Price Monitor" → Credenziali LWA |
| `SPAPI_CLIENT_SECRET` | come sopra |
| `SPAPI_REFRESH_TOKEN` | generato all'autorizzazione dell'app (password manager) |

Le chiavi non vanno mai scritte nel codice, in chat o via email.

## Utenti della dashboard

Supabase → Authentication → Users → *Add user → Create new user* (email + password, "Auto confirm"). Le iscrizioni libere sono disattivate.

## Limiti noti del prototipo

- Alcuni siti (soprattutto Douglas e Sephora) possono bloccare le letture automatiche dai server di GitHub: nella scheda *Raccolte* si vede quali pagine danno errore.
- Le pagine prodotto dei siti autorizzati vanno indicate una volta (scheda *Pagine monitorate*). Amazon invece è automatico tramite EAN.
- La ricerca dei siti sconosciuti e i grafici nel tempo arrivano nelle fasi successive.
