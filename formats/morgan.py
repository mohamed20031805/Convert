import re

def detecter(texte_page1):
    """Retourne True si c'est un PDF Morgan Stanley"""
    return "OPEN POSITIONS" in texte_page1 and "OPEN POSITIONS STATEMENT" not in texte_page1

def extraire_entete(chemin_pdf, template_json=None):
    import pdfplumber, json, os
    with pdfplumber.open(chemin_pdf) as pdf:
        lignes = pdf.pages[0].extract_text().split("\n")

    infos = {"Broker": "", "Client": "", "Close of Business": "", "Account": ""}

    if template_json and os.path.exists(template_json):
        with open(template_json) as f:
            infos.update(json.load(f))

    fin_entete = ["TRADE ACTIVITY", "OPEN POSITIONS", "CASH TRANSACTIONS", "FUTURES CONFIRMATIONS"]

    for ligne in lignes:
        ligne = ligne.strip()
        if not ligne or any(s in ligne for s in fin_entete):
            break
        m = re.search(r'Account\s+([A-Z0-9]+\s*/\s*[A-Z0-9]+)', ligne)
        if m and not infos["Account"]:
            infos["Account"] = m.group(1).strip()
        m = re.search(r'Close of Business\s+(.+)', ligne)
        if m and not infos["Close of Business"]:
            infos["Close of Business"] = m.group(1).strip()

    print(f"\n✅ Entête Morgan : {infos}")
    return infos

def extraire_positions(chemin_pdf):
    import pdfplumber
    toutes_les_lignes = []

    with pdfplumber.open(chemin_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            texte = page.extract_text()
            if not texte or "OPEN POSITIONS" not in texte:
                continue

            col_long_x  = None
            col_short_x = None
            words = page.extract_words()

            for w in words:
                if w['text'] == 'Long'  and col_long_x  is None: col_long_x  = w['x0']
                if w['text'] == 'Short' and col_short_x is None: col_short_x = w['x0']

            if not col_long_x or not col_short_x:
                continue

            lignes_mots = {}
            for w in words:
                y = round(w['top'], 0)
                if y not in lignes_mots: lignes_mots[y] = []
                lignes_mots[y].append(w)

            lignes_dates = {}
            for y in sorted(lignes_mots.keys()):
                mots = lignes_mots[y]
                premier = mots[0]['text']
                if not re.match(r'^\d{2}[A-Z]{3}\d{2}$', premier):
                    continue
                long_val = short_val = ""
                if len(mots) > 1:
                    qte_mot = mots[1]
                    if re.match(r'^\d+$', qte_mot['text']):
                        if abs(qte_mot['x0'] - col_long_x) < abs(qte_mot['x0'] - col_short_x):
                            long_val  = qte_mot['text']
                        else:
                            short_val = qte_mot['text']
                cle = f"{premier}_{mots[-1]['text']}"
                lignes_dates[cle] = (long_val, short_val)

            lignes_texte = texte.split("\n")
            dans_bloc = False

            for ligne in lignes_texte:
                ligne = ligne.strip()
                if re.match(r'^Date\s+Call\s+Price\s+Ref', ligne):
                    dans_bloc = True
                    continue
                if not dans_bloc:
                    continue
                if any(mot in ligne for mot in ["OPEN POSITIONS","No open positions","Continuation","Account","Close of Business","Average","Settlement","Totals"]):
                    continue
                if not re.match(r'^\d{2}[A-Z]{3}\d{2}', ligne):
                    continue

                parsed = _parser_ligne(ligne)
                if not parsed:
                    continue

                cle = f"{parsed['Trade Date']}_{parsed['Trade Ref']}"
                long_val, short_val = lignes_dates.get(cle, ("", ""))
                parsed["Long"]  = long_val
                parsed["Short"] = short_val
                toutes_les_lignes.append(parsed)

    print(f"\n📊 Morgan - Total lignes : {len(toutes_les_lignes)}")
    return toutes_les_lignes

def _parser_ligne(ligne):
    fin = re.compile(r'^(.+?)\s+([-\d,]+\.\d+)\s+([A-Z]{3})\s+([A-Z0-9]+)$')
    m = fin.match(ligne)
    if not m:
        fin2 = re.compile(r'^(.+?)\s+([-\d,]+\.\d+)\s+([A-Z0-9]+)$')
        m = fin2.match(ligne)
        if not m: return None
        debut, mkt_value, ccy, trade_ref = m.group(1).strip(), m.group(2), "", m.group(3)
    else:
        debut, mkt_value, ccy, trade_ref = m.group(1).strip(), m.group(2), m.group(3), m.group(4)

    m2 = re.compile(r'^(\d{2}[A-Z]{3}\d{2})\s+(\d+)\s+([A-Z]{2,4})\s+(.+)$').match(debut)
    if not m2: return None

    m3 = re.compile(r'^(.+?)\s+([A-Z]{3})\s+(\d{2})(?:\s+([\d.V]+[A-Z0-9]*))?(?:\s+([A-Z]+))?$').match(m2.group(4).strip())
    if not m3: return None

    return {
        "Trade Date":   m2.group(1),
        "Long":         "",
        "Short":        "",
        "Exch":         m2.group(3),
        "Product":      m3.group(1).strip(),
        "Mon":          m3.group(2),
        "Yr":           m3.group(3),
        "Strike":       m3.group(4) or "",
        "Put/Call":     m3.group(5) or "",
        "Market Value": mkt_value,
        "CCY":          ccy,
        "Trade Ref":    trade_ref,
    }

def formater_output(lignes):
    """Retourne un DataFrame résumé agrégé par Product"""
    import pandas as pd
    df = pd.DataFrame(lignes)
    df["Long"]  = pd.to_numeric(df["Long"],  errors="coerce").fillna(0).astype(int)
    df["Short"] = pd.to_numeric(df["Short"], errors="coerce").fillna(0).astype(int)
    resume = df.groupby(["Product", "CCY", "Mon", "Yr"], as_index=False).agg(
        Total_Long=("Long", "sum"), Total_Short=("Short", "sum")
    )
    resume["Total_Long"]  = resume["Total_Long"].replace(0, "")
    resume["Total_Short"] = resume["Total_Short"].replace(0, "")
    return resume[["Product", "Total_Long", "Total_Short", "CCY", "Mon", "Yr"]]